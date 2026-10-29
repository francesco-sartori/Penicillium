"""One batch run sample by sample as a DCS would see it: loops with setpoints and modes, alarms, events, lab results.

Independent of the web framework, so it can be tested (and scripted) on its own::

    s = BatchSession()
    s.start(seed=1, fault=5)
    s.set_sp("Fs", 90.0)  # operator setpoint: FIC-101 leaves recipe (CAS) for AUTO
    while s.state is BatchState.RUNNING:
        sample = s.step()

Values are in display units (temperature in degC, volume in m3, weight in t, off-gas O2 in %); setpoints of the
recipe loops come from the batch recipe while the loop is in ``CAS`` and from the operator in ``AUTO``.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from .. import raman
from ..constants import STEP_IN_HOURS
from ..recipe import INPUTS
from ..simulator import Fault, RamanMode, SimulationConfig, Simulator, _ph, _sensor_drift
from ..solvers import SolverError

KELVIN = 273.15
#: PAA setpoint of IndPenSim's PAT controller (fixed in ``Simulator._control``).
PAA_SETPOINT = 1200.0
#: Sample after which IndPenSim's PRBS perturbations take over the sugar and PAA feeds.
_PRBS_START_SAMPLE = 475


class BatchState(str, enum.Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    HELD = "HELD"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


#: Online signals: name -> (tag, description, unit, display range low, high).
SIGNALS: dict[str, tuple[str, str, str, float, float]] = {
    "T": ("TIC-101", "Fermenter temperature", "°C", 20.0, 30.0),
    "pH": ("AIC-101", "Fermenter pH", "pH", 6.0, 7.0),
    "DO2": ("AI-102", "Dissolved oxygen", "mg/L", 0.0, 20.0),
    "O2": ("AI-201", "Off-gas O2", "%", 17.0, 21.0),
    "CO2": ("AI-202", "Off-gas CO2", "%", 0.0, 3.0),
    "Wt": ("WI-101", "Fermenter weight", "t", 50.0, 110.0),
    "V": ("LI-101", "Broth volume", "m³", 40.0, 100.0),
    "pressure": ("PIC-101", "Head-space back pressure", "bar", 0.0, 2.5),
    "Fs": ("FIC-101", "Sugar feed", "L/h", 0.0, 160.0),
    "Foil": ("FIC-102", "Soybean oil feed", "L/h", 0.0, 50.0),
    "Fpaa": ("FIC-103", "PAA precursor feed", "L/h", 0.0, 50.0),
    "Fw": ("FIC-104", "Water for injection", "L/h", 0.0, 600.0),
    "Fg": ("FIC-105", "Aeration", "L/h", 0.0, 100.0),
    "discharge": ("FIC-106", "Broth draw-off", "L/h", 0.0, 5000.0),
    "Fa": ("FI-107", "Acid dosing (pH split range)", "L/h", 0.0, 250.0),
    "Fb": ("FI-108", "Base dosing (pH split range)", "L/h", 0.0, 250.0),
    "Fc": ("FI-109", "Cooling water (TIC split range)", "L/h", 0.0, 1500.0),
    "Fh": ("FI-110", "Hot water (TIC split range)", "L/h", 0.0, 1500.0),
    "RPM": ("SI-101", "Agitator speed", "rpm", 0.0, 150.0),
    "OUR": ("UI-201", "Oxygen uptake rate", "g/min", 0.0, 3.0),
    "CER": ("UI-202", "Carbon evolution rate", "g/h", 0.0, 3.0),
    "PAA_pred": ("AIC-103", "PAA from Raman (PLS soft sensor)", "mg/L", 0.0, 3000.0),
}


@dataclass(frozen=True)
class Loop:
    """A controller the operator can open: ``pv`` names its signal in ``SIGNALS``, setpoints in its unit.

    ``recipe`` loops take their setpoint from the batch recipe in ``CAS`` and from the operator in ``AUTO``.
    ``outputs`` are the signals the controller drives (split range for temperature and pH).
    """

    pv: str
    recipe: bool
    sp_low: float
    sp_high: float
    outputs: tuple[str, ...] = ()
    editable: bool = True


LOOPS: dict[str, Loop] = {
    "Fs": Loop("Fs", True, 0.0, 200.0),
    "Foil": Loop("Foil", True, 0.0, 60.0),
    "Fpaa": Loop("Fpaa", True, 0.0, 50.0),
    "Fw": Loop("Fw", True, 0.0, 1000.0),
    "Fg": Loop("Fg", True, 0.0, 120.0),
    "pressure": Loop("pressure", True, 0.0, 2.5),
    "discharge": Loop("discharge", True, 0.0, 5000.0),
    "T": Loop("T", False, 20.0, 30.0, outputs=("Fc", "Fh")),
    "pH": Loop("pH", False, 6.0, 7.0, outputs=("Fb", "Fa")),
    "PAA": Loop("PAA_pred", False, PAA_SETPOINT, PAA_SETPOINT, outputs=("Fpaa",), editable=False),
}
assert set(INPUTS) <= set(LOOPS)

#: Offline (lab) analyses: name -> (sample tag, description, unit). Simulator channel ``<name>_offline``.
ANALYSES: dict[str, tuple[str, str, str]] = {
    "X": ("QA-301", "Biomass (dry cell weight)", "g/L"),
    "P": ("QA-302", "Penicillin (HPLC)", "g/L"),
    "PAA": ("QA-303", "Phenylacetic acid (HPLC)", "mg/L"),
    "NH3": ("QA-304", "Ammonia nitrogen", "mg/L"),
    "Viscosity": ("QA-305", "Broth viscosity", "cP"),
}


@dataclass(frozen=True)
class AlarmDef:
    """Limit alarm on ``signal`` (or on the PV-SP deviation of loop ``signal`` when ``deviation``).

    The limit is ``offset`` from the setpoint for setpoint-relative alarms, absolute otherwise; the alarm
    clears ``deadband`` inside the limit.
    """

    key: str
    signal: str
    text: str
    priority: int  # 1 urgent, 2 high, 3 medium
    high: bool
    limit: float
    deadband: float
    relative_to_sp: bool = False
    deviation: bool = False
    min_limit: float = 0.0  # deviation alarms: max(limit * |SP|, min_limit)


ALARMS: tuple[AlarmDef, ...] = (
    # IndPenSim's temperature loop is loose: excursions of 1-2 K are normal, so the limits sit above them.
    AlarmDef("T.HH", "T", "Temperature high high", 1, True, 3.0, 0.3, relative_to_sp=True),
    AlarmDef("T.H", "T", "Temperature high", 2, True, 2.2, 0.3, relative_to_sp=True),
    AlarmDef("T.L", "T", "Temperature low", 2, False, -1.5, 0.3, relative_to_sp=True),
    AlarmDef("pH.H", "pH", "pH high", 2, True, 0.2, 0.03, relative_to_sp=True),
    AlarmDef("pH.L", "pH", "pH low", 2, False, -0.2, 0.03, relative_to_sp=True),
    AlarmDef("DO2.LL", "DO2", "Dissolved oxygen low low", 1, False, 3.0, 0.5),
    AlarmDef("DO2.L", "DO2", "Dissolved oxygen low", 2, False, 6.0, 0.5),
    AlarmDef("V.HH", "V", "Broth volume high high", 1, True, 95.0, 1.0),
    AlarmDef("V.H", "V", "Broth volume high", 2, True, 90.0, 1.0),
    AlarmDef("V.L", "V", "Broth volume low", 3, False, 50.0, 1.0),
    AlarmDef("CO2.H", "CO2", "Off-gas CO2 high", 3, True, 2.5, 0.1),
    AlarmDef("Fb.H", "Fb", "Base pump at maximum", 3, True, 224.9, 10.0),
    AlarmDef("PAA_pred.H", "PAA_pred", "PAA high (Raman)", 3, True, 2000.0, 100.0),
    AlarmDef("pressure.D", "pressure", "Back pressure deviation", 2, True, 0.0, 0.0, deviation=True, min_limit=0.2),
    AlarmDef("Fg.D", "Fg", "Aeration flow deviation", 2, True, 0.1, 0.0, deviation=True, min_limit=5.0),
    AlarmDef("Fs.D", "Fs", "Sugar feed deviation", 3, True, 0.1, 0.0, deviation=True, min_limit=5.0),
    AlarmDef("Fpaa.D", "Fpaa", "PAA feed deviation", 3, True, 0.2, 0.0, deviation=True, min_limit=2.0),
)


def _num(x: float | None) -> float | None:
    """JSON-safe number with 6 significant digits (``None`` for missing values)."""
    if x is None:
        return None
    x = float(x)
    if not math.isfinite(x):
        return None
    return float(f"{x:.6g}")


class BatchSession:
    """A batch under DCS control. See the module docstring.

    Args:
        backend: model backend passed to ``Simulator`` (``"auto"``, ``"numba"`` or ``"python"``).
        max_events: length of the event journal kept in memory.
    """

    def __init__(self, backend: str = "auto", max_events: int = 2000):
        self.backend = backend
        self.max_events = max_events
        self.state = BatchState.IDLE
        self.sim: Simulator | None = None
        self.batch_id = 0
        self.settings: dict[str, Any] = {}
        self.started_at: float | None = None  # wall clock (epoch s) at batch start = batch time 0
        self.modes: dict[str, str] = {}
        self._operator_sp: dict[str, float] = {}
        self.time: list[float] = []
        self.history: dict[str, list[float | None]] = {}
        self.lab: list[dict[str, Any]] = []
        self.alarms: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.event_seq = 0
        self.total_yield = 0.0
        self.message = ""

    # ------------------------------------------------------------------ batch control

    def start(
        self,
        seed: int = 1,
        fault: int = 0,
        apc: bool = False,
        prbs: bool = False,
        disturbances: bool = True,
        batch_length_h: float = 230.0,
    ) -> None:
        """Start a new batch (the previous one, if any, is discarded)."""
        config = SimulationConfig(
            fault=Fault(int(fault)),
            raman_mode=RamanMode.PAT_CONTROL if apc else RamanMode.RECORD,
            prbs=bool(prbs),
            disturbances=bool(disturbances),
            batch_length_h=float(batch_length_h),
        )
        self.sim = Simulator(config=config, backend=self.backend)
        self.sim.reset(int(seed))
        self.batch_id += 1
        self.settings = {
            "seed": int(seed),
            "fault": Fault(int(fault)).name,
            "fault_code": int(fault),
            "apc": bool(apc),
            "prbs": bool(prbs),
            "disturbances": bool(disturbances),
            "batch_length_h": float(batch_length_h),
        }
        self.started_at = time.time()
        self.modes = {name: ("CAS" if loop.recipe else "AUTO") for name, loop in LOOPS.items()}
        self._operator_sp = {
            "T": config.temperature_setpoint - KELVIN,
            "pH": config.ph_setpoint,
        }
        self.time = []
        self.history = {name: [] for name in SIGNALS} | {f"{name}.sp": [] for name in LOOPS}
        self.lab = []
        self.alarms = {}
        self.total_yield = 0.0
        self.message = ""
        self.state = BatchState.RUNNING
        options = ", ".join(
            f"{k}={v}" for k, v in self.settings.items() if k not in ("fault_code",) and v not in (False, None)
        )
        self._event("BATCH", "", f"Batch {self.batch_name} started ({options})")

    @property
    def batch_name(self) -> str:
        return f"PEN-{self.batch_id:04d}"

    def hold(self) -> None:
        if self.state is BatchState.RUNNING:
            self.state = BatchState.HELD
            self._event("BATCH", "", f"Batch {self.batch_name} held")

    def resume(self) -> None:
        if self.state is BatchState.HELD:
            self.state = BatchState.RUNNING
            self._event("BATCH", "", f"Batch {self.batch_name} resumed")

    def abort(self) -> None:
        if self.state in (BatchState.RUNNING, BatchState.HELD):
            self.state = BatchState.ABORTED
            self._event("BATCH", "", f"Batch {self.batch_name} aborted by operator at {self.time_h:.1f} h")

    @property
    def time_h(self) -> float:
        return self.sim.time if self.sim is not None else 0.0

    # ------------------------------------------------------------------ operator actions

    def set_mode(self, loop: str, mode: str) -> None:
        """``CAS`` (setpoint from the recipe) or ``AUTO`` (operator setpoint) for a recipe loop."""
        spec = self._loop(loop)
        if not spec.recipe or mode not in ("CAS", "AUTO"):
            raise ValueError(f"{SIGNALS[spec.pv][0]}: mode {mode!r} not available")
        old = self.modes[loop]
        if mode == old:
            return
        if mode == "AUTO":  # bumpless: keep the setpoint the recipe gives now
            self._operator_sp[loop] = self.setpoints()[loop]
        self.modes[loop] = mode
        self._event("OPER", SIGNALS[spec.pv][0], f"Mode {old} -> {mode}")

    def set_sp(self, loop: str, value: float) -> None:
        """Operator setpoint, in the loop's display unit. A recipe loop in ``CAS`` switches to ``AUTO``."""
        spec = self._loop(loop)
        tag = SIGNALS[spec.pv][0]
        value = float(value)
        if not spec.editable:
            raise ValueError(f"{tag}: setpoint is fixed")
        if not (spec.sp_low <= value <= spec.sp_high) or not math.isfinite(value):
            raise ValueError(f"{tag}: setpoint must be within {spec.sp_low:g} .. {spec.sp_high:g}")
        old = self.setpoints().get(loop)
        if spec.recipe and self.modes[loop] == "CAS":
            self.modes[loop] = "AUTO"
            self._event("OPER", tag, "Mode CAS -> AUTO")
        self._operator_sp[loop] = value
        if self.sim is not None and loop == "T":
            self.sim.config = dataclasses.replace(self.sim.config, temperature_setpoint=value + KELVIN)
        elif self.sim is not None and loop == "pH":
            self.sim.config = dataclasses.replace(self.sim.config, ph_setpoint=value)
        unit = SIGNALS[spec.pv][2]
        self._event("OPER", tag, f"SP changed {_fmt(old)} -> {_fmt(value)} {unit}")

    def acknowledge(self, key: str | None = None) -> None:
        """Acknowledge one alarm, or all of them (``key=None``)."""
        for k in list(self.alarms) if key is None else [key]:
            alarm = self.alarms.get(k)
            if alarm is None or alarm["acked"]:
                continue
            alarm["acked"] = True
            self._event("ACK", alarm["tag"], alarm["text"])
            if not alarm["active"]:
                del self.alarms[k]

    # ------------------------------------------------------------------ simulation

    def setpoints(self) -> dict[str, float | None]:
        """Setpoints for the next sample, in display units (``None`` where a loop has none)."""
        sim = self.sim
        if sim is None:
            return {name: None for name in LOOPS}
        recipe = sim.recipe_inputs() if not sim.done else sim.recipe_inputs(sim.k)
        sps: dict[str, float | None] = {}
        for name, spec in LOOPS.items():
            if spec.recipe:
                sps[name] = recipe[name] if self.modes.get(name) == "CAS" else self._operator_sp[name]
            elif name == "PAA":
                sps[name] = PAA_SETPOINT if self.settings.get("apc") else None
            else:
                sps[name] = self._operator_sp[name]
        return sps

    def loop_modes(self) -> dict[str, str]:
        """Modes as displayed: the PRBS and the PAT controller take over feeds whatever the operator chose."""
        modes = dict(self.modes)
        sim = self.sim
        if sim is None:
            return modes
        if self.settings.get("prbs") and sim.k + 1 > _PRBS_START_SAMPLE:
            modes["Fs"] = modes["Fpaa"] = "PRBS"
        if self.settings.get("apc"):
            modes["Fpaa"] = "CAS-AIC" if sim.time + STEP_IN_HOURS >= 10 else modes["Fpaa"]
            modes["PAA"] = "AUTO" if sim.time + STEP_IN_HOURS >= 10 else "MAN"
        else:
            modes["PAA"] = "OFF"
        return modes

    def step(self) -> dict[str, Any]:
        """Simulate one 12-minute sample; returns the new values, lab results and events."""
        if self.state is not BatchState.RUNNING or self.sim is None:
            raise RuntimeError(f"batch is {self.state.value}")
        sim = self.sim
        sps = self.setpoints()
        modes = self.loop_modes()
        inputs = sim.recipe_inputs()
        for name in INPUTS:
            inputs[name] = sps[name]
        first_event = self.event_seq
        try:
            _, reward = sim.step(**inputs)
        except SolverError as exc:
            self.state = BatchState.ABORTED
            self.message = f"Solver failure: {exc}"
            self._event("SYSTEM", "", f"Batch {self.batch_name} aborted: {exc}")
            return {"t": None, "values": {}, "lab": [], "events": self.events_since(first_event)}
        self.total_yield += reward

        values = self._read_values()
        # Where something other than the setpoint drives a flow, the setpoint shown is what is applied.
        for name in ("Fs", "Fpaa"):
            if modes[name] in ("PRBS", "CAS-AIC"):
                sps[name] = values[name]
        for name, sp in sps.items():
            values[f"{name}.sp"] = _num(sp)
        t = _num(sim.time)
        self.time.append(t)
        for name, series in self.history.items():
            series.append(values.get(name))

        new_lab = self._read_lab()
        self._update_alarms(values, sps)
        if sim.done:
            self.state = BatchState.COMPLETE
            harvest = f"harvested penicillin {self.total_yield:,.0f} kg"
            self._event("BATCH", "", f"Batch {self.batch_name} complete; {harvest}")
        return {"t": t, "values": values, "lab": new_lab, "events": self.events_since(first_event)}

    def latest_spectrum(self) -> dict[str, Any] | None:
        """Last Raman spectrum (every second wavenumber), or ``None`` before the first one."""
        if self.sim is None:
            return None
        spectrum = self.sim.latest_spectrum()
        if spectrum is None:
            return None
        return {
            "t": _num(self.sim.time),
            "wavenumber": [_num(w) for w in raman.WAVENUMBER[::2]],
            "intensity": [_num(v) for v in np.asarray(spectrum)[::2]],
        }

    # ------------------------------------------------------------------ views

    def status(self) -> dict[str, Any]:
        sim = self.sim
        over = self.state in (BatchState.COMPLETE, BatchState.ABORTED)
        return {
            "state": self.state.value,
            "batch": self.batch_name if self.batch_id else None,
            "batch_id": self.batch_id,
            "phase": self.phase(),
            "k": sim.k if sim else 0,
            "time_h": _num(self.time_h),
            "length_h": self.settings.get("batch_length_h"),
            "started_at": self.started_at,
            "settings": self.settings,
            "modes": self.loop_modes(),
            "sp": {name: _num(sp) for name, sp in self.setpoints().items()},
            # Harvested penicillin needs the (offline) titre, so it is reported once the batch is over.
            "total_yield_kg": _num(self.total_yield) if over else None,
            "message": self.message,
        }

    def phase(self) -> str:
        if self.sim is None or self.state is BatchState.IDLE:
            return "IDLE"
        if self.state in (BatchState.COMPLETE, BatchState.ABORTED):
            return self.state.value
        t = self.sim.time
        if t < 20:
            return "BATCH GROWTH"
        recipe = self.sim.recipe_inputs()
        if self.setpoints()["discharge"] or recipe["discharge"]:
            return "FED-BATCH / DRAW-OFF"
        return "FED-BATCH"

    def alarm_list(self) -> list[dict[str, Any]]:
        return sorted(self.alarms.values(), key=lambda a: (a["acked"], a["priority"], -a["time_h"]))

    def events_since(self, seq: int) -> list[dict[str, Any]]:
        if seq >= self.event_seq:
            return []
        n = self.event_seq - seq
        return self.events[-n:] if n <= len(self.events) else list(self.events)

    def snapshot(self) -> dict[str, Any]:
        """Everything a newly connected console needs: metadata, status, full history, lab, alarms, events."""
        return {
            "meta": {
                "signals": {
                    name: {"tag": tag, "description": desc, "unit": unit, "low": lo, "high": hi}
                    for name, (tag, desc, unit, lo, hi) in SIGNALS.items()
                },
                "loops": {name: dataclasses.asdict(loop) for name, loop in LOOPS.items()},
                "analyses": {
                    name: {"tag": tag, "description": desc, "unit": unit}
                    for name, (tag, desc, unit) in ANALYSES.items()
                },
                "faults": {f.name: int(f) for f in Fault},
                "step_h": STEP_IN_HOURS,
            },
            "status": self.status(),
            "history": {"t": self.time, **self.history},
            "lab": self.lab,
            "alarms": self.alarm_list(),
            "events": self.events[-500:],
        }

    # ------------------------------------------------------------------ internals

    def _loop(self, loop: str) -> Loop:
        if loop not in LOOPS:
            raise ValueError(f"unknown loop {loop!r}")
        if self.state not in (BatchState.RUNNING, BatchState.HELD):
            raise ValueError("no batch running")
        return LOOPS[loop]

    def _read_values(self) -> dict[str, float | None]:
        sim = self.sim
        k = sim.k
        i = k - 1
        d = sim._data  # the sample just completed; result() would copy every channel each sample
        fault = sim.config.fault
        # A drifting sensor is what the controller (and the operator) sees; IndPenSim records the true value.
        t_drift = _sensor_drift(k, 0.4) if fault == Fault.TEMPERATURE_SENSOR else 0.0
        ph_drift = _sensor_drift(k, 0.1) if fault == Fault.PH_SENSOR else 0.0
        paa_pred = d["PAA_pred"][i - 1] if i >= 1 else math.nan  # filled one sample late
        values = {
            "T": d["T"][i] - t_drift - KELVIN,
            "pH": _ph(d["pH"][i]) - ph_drift,
            "DO2": d["DO2"][i],
            "O2": 100 * d["O2"][i],
            "CO2": d["CO2outgas"][i],
            "Wt": d["Wt"][i] / 1000,
            "V": d["V"][i] / 1000,
            "discharge": abs(d["discharge"][i]),
            "PAA_pred": paa_pred,
        }
        for name in ("pressure", "Fs", "Foil", "Fpaa", "Fw", "Fg", "Fa", "Fb", "Fc", "Fh", "RPM", "OUR", "CER"):
            values[name] = d[name][i]
        return {name: _num(values[name]) for name in SIGNALS}

    def _read_lab(self) -> list[dict[str, Any]]:
        sim = self.sim
        i = sim.k - 1
        d = sim._data
        delay = sim.config.offline_delay_steps
        new = []
        for name, (tag, _, unit) in ANALYSES.items():
            value = d[f"{name}_offline"][i]
            if not math.isfinite(value):
                continue
            entry = {
                "id": len(self.lab) + 1,
                "analysis": name,
                "tag": tag,
                "sample_h": _num((i - delay + 1) * STEP_IN_HOURS),
                "report_h": _num(sim.time),
                "value": _num(value),
                "unit": unit,
            }
            self.lab.append(entry)
            new.append(entry)
        if new:
            self._event("LAB", "", f"Lab results reported for sample taken at {new[0]['sample_h']:.1f} h")
        return new

    def _update_alarms(self, values: dict[str, float | None], sps: dict[str, float | None]) -> None:
        t = self.time_h
        for spec in ALARMS:
            x = values.get(spec.signal)
            if x is None:
                continue
            sp = sps.get(spec.signal)
            if spec.deviation:
                if sp is None:
                    continue
                x = abs(x - sp)
                limit = max(spec.limit * abs(sp), spec.min_limit)
                deadband = 0.2 * limit
            else:
                limit = spec.limit
                if spec.relative_to_sp:
                    if sp is None:
                        continue
                    limit += sp
                deadband = spec.deadband
            alarm = self.alarms.get(spec.key)
            active = alarm is not None and alarm["active"]
            if spec.high:
                condition = x > (limit - deadband if active else limit)
            else:
                condition = x < (limit + deadband if active else limit)
            tag = SIGNALS[spec.signal][0]
            if condition and not active:
                self.alarms[spec.key] = {
                    "key": spec.key,
                    "tag": tag,
                    "text": spec.text,
                    "priority": spec.priority,
                    "active": True,
                    "acked": False,
                    "time_h": _num(t),
                    "value": _num(x),
                    "limit": _num(limit),
                }
                self._event("ALARM", tag, f"{spec.text} ({_fmt(x)}, limit {_fmt(limit)})", spec.priority)
            elif not condition and active:
                alarm["active"] = False
                self._event("RTN", tag, spec.text, spec.priority)
                if alarm["acked"]:
                    del self.alarms[spec.key]

    def _event(self, kind: str, tag: str, text: str, priority: int | None = None) -> None:
        self.event_seq += 1
        # Plant time (epoch s), so events of earlier batches keep their own clock.
        at = (self.started_at if self.started_at is not None else time.time()) + self.time_h * 3600
        self.events.append(
            {"seq": self.event_seq, "time_h": _num(self.time_h), "at": at, "batch": self.batch_name, "kind": kind,
             "tag": tag, "text": text, "priority": priority}
        )  # fmt: skip
        if len(self.events) > self.max_events:
            del self.events[: len(self.events) - self.max_events]


def _fmt(x: float | None) -> str:
    return "---" if x is None else f"{x:.4g}"
