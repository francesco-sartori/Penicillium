"""Web server of the operator console: serves the React front end and streams the batch over a WebSocket.

Protocol (JSON messages on ``/ws``):

* server -> client: ``snapshot`` on connect (metadata, history, lab, alarms, events, speed); ``update`` after
  each tick (new samples, status, alarms, events); ``status`` after a command; ``spectrum``; ``error``.
* client -> server: ``{"cmd": ...}`` with ``start`` (seed, fault, apc, prbs, disturbances, batch_length_h),
  ``hold``, ``resume``, ``abort``, ``speed`` (value), ``set_mode`` (loop, mode), ``set_sp`` (loop, value),
  ``ack`` (key, or none for all), ``spectrum``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..constants import STEP_IN_MINUTES
from .session import BatchSession, BatchState

STATIC_DIR = Path(__file__).parent / "static"
#: Wall-clock seconds of one sample at real time (1x).
SAMPLE_SECONDS = STEP_IN_MINUTES * 60
#: Shortest interval between two updates sent to the consoles; faster speeds send several samples per update.
TICK_SECONDS = 0.05
#: Speed factors offered by the console (simulated time / wall time).
SPEEDS = (1, 10, 60, 360, 1800, 3600, 18000, 36000)

_NOT_BUILT = """<!doctype html><title>Console not built</title>
<body style="font-family:sans-serif;padding:2em"><h1>Front end not built</h1>
<p>Build it once with <code>cd webapp &amp;&amp; npm install &amp;&amp; npm run build</code>,
or run the Vite dev server (<code>npm run dev</code>) next to this server.</p></body>"""


class Runner:
    """Steps the session in real time (times ``speed``) and broadcasts to every connected console."""

    def __init__(self, session: BatchSession, speed: float = 360):
        self.session = session
        self.speed = float(speed)
        self.clients: set[WebSocket] = set()
        self._wake = asyncio.Event()
        self._events_sent = 0

    def wake(self) -> None:
        self._wake.set()

    async def _sleep(self, timeout: float | None) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout)
        self._wake.clear()

    async def run(self) -> None:
        last = time.perf_counter()
        while True:
            if self.session.state is not BatchState.RUNNING:
                await self._sleep(None)
                last = time.perf_counter()
                continue
            period = SAMPLE_SECONDS / self.speed
            n = max(1, int(TICK_SECONDS / period))
            now = time.perf_counter()
            due = last + n * period
            if now < due:
                await self._sleep(due - now)  # woken early by a command: re-check speed and state
                continue
            last = now
            await self.advance(n)

    async def advance(self, n: int) -> None:
        samples = []
        for _ in range(n):
            if self.session.state is not BatchState.RUNNING:
                break
            samples.append(self.session.step())
        await self.broadcast({"type": "update", "samples": samples, **self._state()})

    def _state(self) -> dict[str, Any]:
        s = self.session
        events = s.events_since(self._events_sent)
        self._events_sent = s.event_seq
        return {"status": self.status(), "alarms": s.alarm_list(), "events": events}

    def status(self) -> dict[str, Any]:
        return {**self.session.status(), "speed": self.speed, "speeds": list(SPEEDS)}

    def snapshot(self) -> dict[str, Any]:
        snap = self.session.snapshot()
        snap["status"] = self.status()
        return {"type": "snapshot", **snap}

    async def broadcast(self, message: dict[str, Any]) -> None:
        text = json.dumps(message, allow_nan=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:  # client went away mid-send
                self.clients.discard(ws)

    async def command(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        s = self.session
        cmd = msg.get("cmd")
        if cmd == "start":
            args = {k: msg[k] for k in ("seed", "fault", "apc", "prbs", "disturbances", "batch_length_h") if k in msg}
            s.start(**args)
            self._events_sent = s.event_seq  # the snapshot carries the events so far
            await self.broadcast(self.snapshot())
            await self.advance(1)  # first sample now, not one period later
            self.wake()
            return
        if cmd == "spectrum":
            await ws.send_text(json.dumps({"type": "spectrum", "spectrum": s.latest_spectrum()}, allow_nan=False))
            return
        if cmd == "hold":
            s.hold()
        elif cmd == "resume":
            s.resume()
        elif cmd == "abort":
            s.abort()
        elif cmd == "speed":
            speed = float(msg["value"])
            if not 0 < speed <= max(SPEEDS):
                raise ValueError(f"speed must be in (0, {max(SPEEDS)}]")
            self.speed = speed
        elif cmd == "set_mode":
            s.set_mode(msg["loop"], msg["mode"])
        elif cmd == "set_sp":
            s.set_sp(msg["loop"], msg["value"])
        elif cmd == "ack":
            s.acknowledge(msg.get("key"))
        else:
            raise ValueError(f"unknown command {cmd!r}")
        self.wake()
        await self.broadcast({"type": "status", **self._state()})


def create_app(backend: str = "auto", speed: float = 360) -> FastAPI:
    """The console's ASGI app (one batch session shared by every browser that connects)."""
    session = BatchSession(backend=backend)
    runner = Runner(session, speed=speed)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Compile the model before the first batch (a few seconds the first time, cached afterwards).
        await asyncio.to_thread(_warm_up, backend)
        task = asyncio.create_task(runner.run())
        yield
        task.cancel()

    app = FastAPI(title="Penicillium DCS console", lifespan=lifespan)
    app.state.runner = runner

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        runner.clients.add(ws)
        await ws.send_text(json.dumps(runner.snapshot(), allow_nan=False))
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                try:
                    await runner.command(ws, msg)
                except (ValueError, KeyError, TypeError) as exc:
                    await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except WebSocketDisconnect:
            pass
        finally:
            runner.clients.discard(ws)

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def not_built() -> HTMLResponse:
            return HTMLResponse(_NOT_BUILT)

    return app


def _warm_up(backend: str) -> None:
    from ..simulator import Simulator

    sim = Simulator(backend=backend)
    sim.reset(0)
    sim.step(**sim.recipe_inputs())


def serve(host: str = "127.0.0.1", port: int = 8050, backend: str = "auto", open_browser: bool = True) -> None:
    """Run the console with uvicorn and open it in the browser."""
    import uvicorn

    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    print(f"Penicillium DCS console on {url} (Ctrl+C to stop)")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(backend=backend), host=host, port=port, log_level="warning")
