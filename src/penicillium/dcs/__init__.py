"""Operator console in the style of a DCS operator workplace: one batch simulated in real time in a web app.

Run it with ``penicillium dcs`` (needs the ``dcs`` extra: ``pip install "penicillium[dcs]"``) and open the
address it prints. ``session`` holds the plant logic (loops, alarms, lab results) and does not depend on the web
framework; ``server`` streams it over a WebSocket to the React front end, whose built files live in ``static/``.
"""

from .session import ANALYSES, LOOPS, BatchSession, BatchState

__all__ = ["ANALYSES", "LOOPS", "BatchSession", "BatchState"]
