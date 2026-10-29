"""Operator console: batch session (loops, alarms, lab results) and the WebSocket server."""

import json
import math

import pytest

from penicillium.dcs import ANALYSES, LOOPS, BatchSession, BatchState
from penicillium.dcs.session import SIGNALS


def run_to_end(s: BatchSession) -> list[dict]:
    samples = []
    while s.state is BatchState.RUNNING:
        samples.append(s.step())
    return samples


def test_idle_session_has_no_setpoints():
    s = BatchSession()
    assert s.state is BatchState.IDLE
    assert s.status()["sp"] == {name: None for name in LOOPS}
    with pytest.raises(ValueError, match="no batch"):
        s.set_sp("Fs", 50)


def test_step_reports_values_setpoints_and_lab():
    s = BatchSession()
    s.start(seed=1, batch_length_h=13)
    samples = run_to_end(s)
    assert s.state is BatchState.COMPLETE
    assert len(samples) == len(s.time) == 65
    first = samples[0]["values"]
    assert set(SIGNALS) <= set(first)
    assert first["T.sp"] == pytest.approx(298 - 273.15)
    assert first["Fs.sp"] == 8.0  # IndPenSim recipe up to 3 h
    assert first["PAA.sp"] is None  # no PAT control
    # Lab results at 1 h, 12 h and at the end, each reporting a sample taken 0.8 h earlier.
    sample_times = sorted({r["sample_h"] for r in s.lab})
    assert sample_times == pytest.approx([0.2, 11.2, 12.2])
    assert {r["analysis"] for r in s.lab} == set(ANALYSES)
    assert s.status()["total_yield_kg"] is not None
    # JSON-safe throughout (NaN becomes None).
    json.dumps(s.snapshot(), allow_nan=False)


def test_operator_setpoint_drives_the_feed():
    s = BatchSession()
    s.start(seed=2, batch_length_h=6)
    s.step()
    s.set_sp("Fs", 42.0)
    assert s.modes["Fs"] == "AUTO"
    sample = s.step()
    assert sample["values"]["Fs"] == 42.0
    assert sample["values"]["Fs.sp"] == 42.0
    s.set_mode("Fs", "CAS")
    sample = s.step()
    assert sample["values"]["Fs"] == sample["values"]["Fs.sp"] == 8.0
    kinds = [(e["kind"], e["tag"]) for e in s.events]
    assert ("OPER", "FIC-101") in kinds


def test_auto_mode_is_bumpless():
    s = BatchSession()
    s.start(seed=2, batch_length_h=30)
    for _ in range(60):  # to 12 h: sugar feed recipe 15 L/h
        s.step()
    before = s.setpoints()["Fs"]
    s.set_mode("Fs", "AUTO")
    assert s.setpoints()["Fs"] == before


def test_temperature_setpoint_reaches_the_controller():
    s = BatchSession()
    s.start(seed=3, batch_length_h=40)
    s.set_sp("T", 26.0)
    assert s.sim.config.temperature_setpoint == pytest.approx(26.0 + 273.15)
    run_to_end(s)
    assert s.history["T"][-1] == pytest.approx(26.0, abs=0.7)


def test_setpoint_limits_and_fixed_setpoints():
    s = BatchSession()
    s.start(seed=1, apc=True, batch_length_h=2)
    with pytest.raises(ValueError, match="within"):
        s.set_sp("pH", 9.0)
    with pytest.raises(ValueError, match="fixed"):
        s.set_sp("PAA", 1000)
    with pytest.raises(ValueError, match="not available"):
        s.set_mode("T", "CAS")


def test_sensor_drift_is_what_the_operator_sees():
    s = BatchSession()
    s.start(seed=1, fault=7, batch_length_h=200)  # temperature sensor reads low by up to 0.4 K
    run_to_end(s)
    true_T = s.sim.result()["T"][-1] - 273.15
    assert s.history["T"][-1] == pytest.approx(true_T - 0.4, abs=1e-4)


def test_coolant_fault_raises_and_clears_temperature_alarms():
    s = BatchSession()
    s.start(seed=1, fault=5)
    run_to_end(s)
    raised = [e for e in s.events if e["kind"] == "ALARM" and e["tag"] == "TIC-101"]
    assert raised and min(e["time_h"] for e in raised) > 60  # coolant fault from sample 350 (70 h)
    returned = [e for e in s.events if e["kind"] == "RTN" and e["tag"] == "TIC-101"]
    assert returned
    # Returned but unacknowledged alarms stay listed until acknowledged.
    assert all(not a["active"] for a in s.alarm_list())
    s.acknowledge()
    assert s.alarm_list() == []


def test_nominal_batch_is_quiet():
    s = BatchSession()
    s.start(seed=1)
    run_to_end(s)
    alarms = [e for e in s.events if e["kind"] == "ALARM"]
    assert len(alarms) <= 2


def test_acknowledge_active_alarm_keeps_it_listed():
    s = BatchSession()
    s.start(seed=1, fault=1, batch_length_h=22)  # aeration drops to 20 from sample 100 (20 h) to 120
    run_to_end(s)
    active = [a for a in s.alarm_list() if a["active"]]
    assert active
    s.acknowledge(active[0]["key"])
    assert s.alarms[active[0]["key"]]["acked"]


def test_prbs_and_apc_take_over_the_feeds():
    s = BatchSession()
    s.start(seed=1, prbs=True, apc=True, batch_length_h=100)
    run_to_end(s)
    modes = s.loop_modes()
    assert modes["Fs"] == "PRBS"
    assert modes["Fpaa"] == "CAS-AIC"  # the PAT controller overrides the PRBS on the PAA feed
    assert modes["PAA"] == "AUTO"
    assert s.history["PAA.sp"][-1] == 1200
    assert s.history["PAA_pred"][-1] is not None and math.isfinite(s.history["PAA_pred"][-1])
    assert s.latest_spectrum()["intensity"]


def test_hold_resume_abort():
    s = BatchSession()
    s.start(seed=1, batch_length_h=2)
    s.hold()
    with pytest.raises(RuntimeError):
        s.step()
    s.resume()
    s.step()
    s.abort()
    assert s.state is BatchState.ABORTED
    assert [e["kind"] for e in s.events].count("BATCH") == 4


# ---------------------------------------------------------------------- server

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from penicillium.dcs.server import create_app

    with TestClient(create_app()) as c:
        yield c


def receive_until(ws, kind):
    while True:
        msg = json.loads(ws.receive_text())
        if msg["type"] == kind:
            return msg


def test_websocket_protocol(client):
    with client.websocket_connect("/ws") as ws:
        snap = json.loads(ws.receive_text())
        assert snap["type"] == "snapshot"
        assert snap["status"]["state"] == "IDLE"
        assert set(snap["meta"]["signals"]) == set(SIGNALS)

        ws.send_text(json.dumps({"cmd": "speed", "value": 36000}))
        assert receive_until(ws, "status")["status"]["speed"] == 36000

        ws.send_text(json.dumps({"cmd": "start", "seed": 1, "batch_length_h": 3}))
        snap = receive_until(ws, "snapshot")
        assert snap["status"]["state"] == "RUNNING"
        n = 0
        while True:
            msg = receive_until(ws, "update")
            n += sum(1 for s in msg["samples"] if s["t"] is not None)
            if msg["status"]["state"] == "COMPLETE":
                break
        assert n == 15

        ws.send_text(json.dumps({"cmd": "set_sp", "loop": "Fs", "value": 1e6}))
        assert receive_until(ws, "error")["message"]


def test_index_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower() or "not built" in r.text.lower()
