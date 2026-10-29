"""Ready-made campaigns for the common uses of IndPenSim, each one call returning a tidy ``Campaign``.

    from penicillium import scenarios

    camp = scenarios.fault_campaign(n_normal=20, n_per_fault=5, seed=0)  # anomaly detection / diagnosis
    camp = scenarios.soft_sensor_campaign(n_batches=10, seed=0)  # Raman + delayed lab data
    camp = scenarios.goldrick2019_campaign(seed=0)  # the structure of the published 100-batch data set
    camp.samples  # one row per batch and sample: batch_id, time_h, labels, all channels
    camp.batches  # one row per batch: seed, fault, length, yield, fault onset...
    train_ids, test_ids = camp.split(test_fraction=0.3)  # by batch, stratified by fault

Every campaign is reproducible from ``seed`` on any platform: batch ``i`` gets the seed ``seed * 100_000 + i``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .batches import BatchSpec, simulate_batches
from .constants import STEP_IN_HOURS
from .noise import MeasurementNoise
from .raman import WAVENUMBER
from .result import LAB_CHANNELS, BatchResult
from .simulator import MAX_BATCH_LENGTH_H, SINGLE_FAULTS, Fault, RamanMode, SimulationConfig

# SINGLE_FAULTS (the default faults of fault_campaign) and LAB_CHANNELS are also importable from this module.

#: Channels a plant measures online (no hidden model states), useful as features for monitoring models.
ONLINE_CHANNELS: tuple[str, ...] = (
    "Fs", "Foil", "Fg", "pressure", "discharge", "Fw", "Fpaa", "Fa", "Fb", "Fc", "Fh", "RPM",
    "DO2", "O2", "V", "Wt", "pH", "T", "CO2outgas", "OUR", "CER",
)  # fmt: skip


@dataclass
class Campaign:
    """Simulated batches in tidy form.

    Attributes:
        samples: one row per batch and sample. Columns: ``batch_id``, ``time_h``, ``fault`` (batch fault code),
            ``fault_active`` (0/1 label per sample), ``kind`` and every channel of ``penicillium.CHANNELS``. With
            measurement noise, the channels hold the measurements and ``<channel>_true`` the exact values.
        batches: one row per batch: ``batch_id``, ``seed``, ``kind``, ``fault``, ``fault_name``,
            ``batch_length_h``, ``total_yield_kg``, ``final_penicillin_g_per_L``, ``fault_onset_h`` (first sample
            with an active fault, NaN for normal batches).
        lab: off-line measurements in long form: ``batch_id``, ``sample_time_h`` (when the broth was sampled),
            ``available_time_h`` (when the result is reported), and the values (with measurement noise, also
            ``<assay>_true``).
        raman: Raman spectra per ``batch_id`` (samples x wavenumbers, wavenumbers as ``raman_wavenumber``), when
            recorded.
    """

    samples: pd.DataFrame
    batches: pd.DataFrame
    lab: pd.DataFrame
    raman: dict[int, np.ndarray] | None = None
    raman_wavenumber: np.ndarray = field(default_factory=lambda: WAVENUMBER.copy())
    description: str = ""

    def split(self, test_fraction: float = 0.3, seed: int = 0) -> tuple[list[int], list[int]]:
        """Split batch ids into train and test sets, by batch (never by sample) and stratified by fault."""
        rng = np.random.default_rng(seed)
        train: list[int] = []
        test: list[int] = []
        for _, group in self.batches.groupby("fault", sort=True):
            ids = rng.permutation(group["batch_id"].to_numpy())
            n_test = round(len(ids) * test_fraction)
            test.extend(int(i) for i in ids[:n_test])
            train.extend(int(i) for i in ids[n_test:])
        return sorted(train), sorted(test)

    def online(self) -> pd.DataFrame:
        """``samples`` restricted to labels and online measurements (what a monitoring model may use)."""
        return self.samples[["batch_id", "time_h", "kind", "fault", "fault_active", *ONLINE_CHANNELS]]

    def save(self, directory: str | Path) -> Path:
        """Write ``samples.parquet``, ``batches.csv``, ``lab.csv``, ``raman/<batch_id>.npy`` and ``campaign.json``."""
        from ._version import __version__

        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        self.samples.to_parquet(out / "samples.parquet")
        self.batches.to_csv(out / "batches.csv", index=False)
        self.lab.to_csv(out / "lab.csv", index=False)
        if self.raman:
            (out / "raman").mkdir(exist_ok=True)
            np.save(out / "raman" / "wavenumber.npy", self.raman_wavenumber)
            for batch_id, spectra in self.raman.items():
                np.save(out / "raman" / f"{batch_id}.npy", spectra.astype(np.float32))
        meta = {"generator": "penicillium", "version": __version__, "description": self.description}
        (out / "campaign.json").write_text(json.dumps(meta, indent=2))
        return out


def build_campaign(
    specs: Sequence[BatchSpec],
    kinds: Sequence[str] | None = None,
    n_jobs: int | None = None,
    keep_raman: bool = False,
    description: str = "",
    progress: Callable[[int, int, BatchResult], None] | None = None,
    measurement_noise: MeasurementNoise | None = None,
) -> Campaign:
    """Simulate ``specs`` in parallel and collect them into a ``Campaign`` (batch ids 1, 2, ...).

    ``measurement_noise`` adds sensor and assay errors to the online and lab channels, seeded by each batch's seed.
    """
    results = simulate_batches(specs, n_jobs=n_jobs, progress=progress, keep_raman=keep_raman)
    if measurement_noise is not None:
        results = [measurement_noise.apply(res, seed=spec.seed) for spec, res in zip(specs, results, strict=True)]
    kinds = list(kinds) if kinds is not None else ["custom"] * len(results)
    frames, rows, labs = [], [], []
    raman: dict[int, np.ndarray] = {}
    for batch_id, (spec, kind, res) in enumerate(zip(specs, kinds, results, strict=True), start=1):
        df = res.to_pandas().reset_index()
        for name, values in res.truth.items():
            df[f"{name}_true"] = values
        fault = int(spec.config.fault)
        df.insert(0, "batch_id", batch_id)
        df.insert(2, "kind", kind)
        df.insert(3, "fault", fault)
        df.insert(4, "fault_active", res["Fault_ref"].astype(np.int8))
        frames.append(df)
        active = np.flatnonzero(res["Fault_ref"] > 0)
        rows.append({
            "batch_id": batch_id, "seed": spec.seed, "kind": kind, "fault": fault, "fault_name": Fault(fault).name,
            "batch_length_h": spec.config.batch_length_h, "total_yield_kg": res.total_yield,
            "final_penicillin_g_per_L": float(res["P"][-1]),
            "fault_onset_h": float(res.time[active[0]]) if len(active) else np.nan,
        })  # fmt: skip
        labs.append(_lab_table(res, batch_id, spec.config))
        if keep_raman and res.raman is not None:
            raman[batch_id] = res.raman
    samples = pd.concat(frames, ignore_index=True)
    samples["kind"] = samples["kind"].astype("category")
    return Campaign(
        samples=samples,
        batches=pd.DataFrame(rows),
        lab=pd.concat(labs, ignore_index=True),
        raman=raman or None,
        description=description,
    )


def _lab_table(res: BatchResult, batch_id: int, config: SimulationConfig) -> pd.DataFrame:
    reported = np.flatnonzero(~np.isnan(res["P_offline"]))
    delay = config.offline_delay_steps * STEP_IN_HOURS
    table = pd.DataFrame({
        "batch_id": batch_id,
        "sample_time_h": res.time[reported] - delay,
        "available_time_h": res.time[reported],
        **{name.removesuffix("_offline"): res[name][reported] for name in LAB_CHANNELS},
    })  # fmt: skip
    for name in LAB_CHANNELS:
        if name in res.truth:
            table[f"{name.removesuffix('_offline')}_true"] = res.truth[name][reported]
    return table


def _seed(seed: int, i: int) -> int:
    return seed * 100_000 + i


def variable_batch_lengths(n: int, seed: int, mean: float = 230.0, sd: float = 25.0) -> list[float]:
    """Batch lengths drawn as IndPenSim does for uneven batches (``round(230 + 25 * randn)`` hours)."""
    rng = np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(7,)))
    lengths = np.round(rng.normal(mean, sd, n))
    return [float(v) for v in np.clip(lengths, 1.0, MAX_BATCH_LENGTH_H)]


def fault_campaign(
    n_normal: int = 20,
    n_per_fault: int = 5,
    faults: Sequence[Fault] = SINGLE_FAULTS,
    seed: int = 0,
    config: SimulationConfig | None = None,
    n_jobs: int | None = None,
    measurement_noise: MeasurementNoise | None = None,
) -> Campaign:
    """Normal and faulty batches with per-sample fault labels, for fault detection and diagnosis.

    Faulty batches use IndPenSim's fault profiles (``penicillium.Fault``); ``samples.fault_active`` marks the
    samples where the fault acts, ``batches.fault_onset_h`` the first one. ``config`` sets everything else
    (default: IndPenSim defaults without Raman); ``measurement_noise`` adds sensor and assay errors (see
    ``build_campaign``).
    """
    base = config if config is not None else SimulationConfig(raman_mode=RamanMode.OFF)
    plan = [Fault.NONE] * n_normal + [Fault(f) for f in faults for _ in range(n_per_fault)]
    specs = [BatchSpec(seed=_seed(seed, i), config=replace(base, fault=f)) for i, f in enumerate(plan, start=1)]
    kinds = ["normal" if f == Fault.NONE else "fault" for f in plan]
    return build_campaign(
        specs, kinds, n_jobs=n_jobs, description=f"fault_campaign(seed={seed})", measurement_noise=measurement_noise
    )


def soft_sensor_campaign(
    n_batches: int = 10,
    seed: int = 0,
    prbs: bool = True,
    config: SimulationConfig | None = None,
    n_jobs: int | None = None,
    measurement_noise: MeasurementNoise | None = None,
) -> Campaign:
    """Batches with Raman spectra and delayed off-line lab results, for soft sensors (e.g. penicillin or PAA).

    ``campaign.raman[batch_id]`` holds the spectra (one per 12-minute sample), ``campaign.lab`` the lab results
    with the time the broth was sampled and the time the result became available (4 samples later, as in
    IndPenSim). With ``prbs=True`` (default) the feeds are perturbed as in IndPenSim's operator-controlled batches,
    which makes regression models more identifiable. About 20 MB of spectra per batch. ``measurement_noise`` adds
    sensor and assay errors to the online channels and the lab results (see ``build_campaign``).
    """
    base = config if config is not None else SimulationConfig(raman_mode=RamanMode.RECORD)
    if base.raman_mode == RamanMode.OFF:
        raise ValueError("a soft-sensor campaign needs Raman spectra; use raman_mode RECORD or PAT_CONTROL")
    base = replace(base, prbs=prbs)
    specs = [BatchSpec(seed=_seed(seed, i), config=base) for i in range(1, n_batches + 1)]
    return build_campaign(
        specs, ["soft_sensor"] * n_batches, n_jobs=n_jobs, keep_raman=True,
        description=f"soft_sensor_campaign(seed={seed})", measurement_noise=measurement_noise,
    )  # fmt: skip


def goldrick2019_campaign(
    seed: int = 0,
    n_per_strategy: int = 30,
    n_faults: int = 10,
    variable_length: bool = True,
    raman: bool = False,
    n_jobs: int | None = None,
    measurement_noise: MeasurementNoise | None = None,
) -> Campaign:
    """A campaign with the structure of the published IndPenSim 100-batch data set (Goldrick et al., 2019).

    Batches ``1..30`` recipe driven, ``31..60`` operator controlled (PRBS feeds), ``61..90`` advanced process
    control of PAA (``RamanMode.PAT_CONTROL``), ``91..100`` with faults (IndPenSim's single faults in turn).
    Lengths vary as in IndPenSim (``230 + 25 randn`` h) unless ``variable_length=False``. ``raman=True`` records
    the spectra of every batch (about 20 MB each). ``measurement_noise`` adds sensor and assay errors (see
    ``build_campaign``).
    """
    n = n_per_strategy
    lengths = variable_batch_lengths(3 * n + n_faults, seed) if variable_length else [230.0] * (3 * n + n_faults)
    rec = RamanMode.RECORD if raman else RamanMode.OFF
    plan: list[tuple[str, SimulationConfig]] = []
    plan += [("recipe", SimulationConfig(raman_mode=rec))] * n
    plan += [("operator", SimulationConfig(raman_mode=rec, prbs=True))] * n
    plan += [("apc", SimulationConfig(raman_mode=RamanMode.PAT_CONTROL))] * n
    plan += [("fault", SimulationConfig(raman_mode=rec, fault=SINGLE_FAULTS[i % len(SINGLE_FAULTS)]))
             for i in range(n_faults)]  # fmt: skip
    specs = [
        BatchSpec(seed=_seed(seed, i), config=replace(cfg, batch_length_h=length))
        for i, ((_, cfg), length) in enumerate(zip(plan, lengths, strict=True), start=1)
    ]
    return build_campaign(
        specs, [kind for kind, _ in plan], n_jobs=n_jobs, keep_raman=raman,
        description=f"goldrick2019_campaign(seed={seed})", measurement_noise=measurement_noise,
    )  # fmt: skip


def control_benchmark(
    policy: Callable | None = None,
    n_batches: int = 10,
    seed: int = 1000,
    env_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Evaluate a control policy on fixed test batches of the Gymnasium environment (needs ``[gym]``).

    ``policy(obs, env) -> action``; default: the IndPenSim recipe (the baseline to beat). Returns one row per
    batch with the yield, the number of steps and whether the batch failed. Use the same ``seed`` for every
    policy you compare: the batches (initial state, parameters, disturbances) are then identical.
    """
    from .envs import IndPenSimEnv

    env = IndPenSimEnv(**(env_kwargs or {}))
    rows = []
    for i in range(n_batches):
        obs, info = env.reset(seed=_seed(seed, i + 1))
        done, steps, failed = False, 0, False
        while not done:
            action = env.recipe_action() if policy is None else policy(obs, env)
            obs, _, terminated, truncated, info = env.step(action)
            steps += 1
            failed = failed or "error" in info
            done = terminated or truncated
        rows.append({"batch": i + 1, "yield_kg": info["total_yield_kg"], "steps": steps, "failed": failed})
    return pd.DataFrame(rows)
