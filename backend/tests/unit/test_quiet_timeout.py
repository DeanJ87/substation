"""A long Siril command that keeps printing isn't cut off by its timeout; one that goes quiet is (IC 4605 v5,
2026-10-14: a mosaic stack was stopped at 86% after two hours while still reporting progress)."""

from __future__ import annotations

import queue
import threading
import time

import pytest

from apps.engine.siril import EngineError, Siril


def _engine() -> Siril:
    s = Siril.__new__(Siril)
    s._lines = queue.Queue()
    s._stdout = []
    s.proc = None
    s.alive = lambda: True  # type: ignore[method-assign]
    s._stop_if_cancelled = lambda command: None  # type: ignore[method-assign]
    return s


def _feed(s: Siril, lines: list[str], every: float) -> None:
    def go() -> None:
        for line in lines:
            time.sleep(every)
            s._lines.put(line)

    threading.Thread(target=go, daemon=True).start()


def test_quiet_mode_keeps_going_while_siril_reports():
    s = _engine()
    _feed(s, [f"progress: {i}%" for i in range(5)] + ["status: success stack"], every=0.4)
    got = s._wait(lambda line: line.startswith("status:"), 1.2, "stack r_sub_", quiet=True)
    assert got[-1] == "status: success stack"  # took ~2.4 s against a 1.2 s timeout


def test_plain_timeout_is_total_and_quiet_stops_on_silence():
    s = _engine()
    _feed(s, [f"progress: {i}%" for i in range(5)], every=0.4)
    with pytest.raises(EngineError, match="took longer"):
        s._wait(lambda line: False, 1.2, "stack r_sub_")
    q = _engine()
    with pytest.raises(EngineError, match="printed nothing"):
        q._wait(lambda line: False, 1.0, "stack r_sub_", quiet=True)
