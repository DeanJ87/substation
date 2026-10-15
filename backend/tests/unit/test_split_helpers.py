"""005-DR-29: the pieces split out of the supervisor, the stack and the settings checks behave as before."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from apps.libraries.api import _check_installation, _clean_processing
from apps.processing.masters import _stack_command, _superseded_reason
from substation.api import ApiError
from substation.tasks.activity import outcome
from substation.tasks.management.commands import supervise


class FakeProc:
    def __init__(self, alive: bool = True, code: int = 0):
        self._alive, self.returncode = alive, code
        self.signals: list[int] = []

    def poll(self):
        return None if self._alive else self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self._alive = False


def test_scale_starts_missing_workers_and_retires_surplus(monkeypatch):
    started = []

    def start(self):
        started.append(self.name)
        self.proc = FakeProc()

    monkeypatch.setattr(supervise.Child, "start", start)
    workers: dict[int, supervise.Child] = {}
    supervise._scale(workers, 3, 1, "host")
    assert started == ["worker-0", "worker-1", "worker-2"]
    assert "--heavy-slots" in workers[0].argv and "host-worker-0" in workers[0].argv
    supervise._scale(workers, 1, 1, "host")  # surplus told to stop, and dropped once they have
    assert set(workers) == {0}


def test_a_crashed_child_waits_before_restarting(monkeypatch):
    c = supervise.Child("watcher", ["x"])
    c.proc = cast(Any, FakeProc(alive=False, code=1))
    c.started_at = supervise.time.monotonic()  # died within a minute: backoff
    supervise._restart_crashed([c])
    assert c.proc is None and c.restarts == 1 and c.next_start > supervise.time.monotonic()


def test_fixed_children_follow_the_options(monkeypatch):
    monkeypatch.delenv("SUBSTATION_ONLY_QUEUES", raising=False)
    names = [c.name for c in supervise._fixed_children(web=True, watcher=False)]
    assert names == ["web"]
    monkeypatch.setenv("SUBSTATION_ONLY_QUEUES", "finish")
    names = [c.name for c in supervise._fixed_children(web=False, watcher=False)]
    assert names == ["control"]


def _mm(exp):
    return SimpleNamespace(included=True, frame=SimpleNamespace(exptime_s=exp))


def test_stack_command_weights_mixed_exposures_by_noise():
    m = cast(Any, SimpleNamespace(recipe={"options": {"weighting": "grade", "sigma": [2.5, 3]}}))
    notes: list[str] = []
    cmd = _stack_command(m, cast(Any, {1: _mm(60), 2: _mm(240)}), notes, None, Path("/o/master_v1"))
    assert "-weight=noise" in cmd and "rej w 2.5 3" in cmd and "  " not in cmd
    assert notes and notes[0].startswith("Mixed exposures (60 s, 240 s)")
    mosaic = _stack_command(m, cast(Any, {1: _mm(60), 2: _mm(60)}), [], "Mosaic", Path("/o/m"))
    assert "-weight=wfwhm" in mosaic and "-maximize -overlap_norm -feather=100" in mosaic


def test_superseded_reason_counts_the_difference():
    m = cast(Any, SimpleNamespace(version=4))
    assert (
        _superseded_reason(m, cast(Any, SimpleNamespace(sub_count=20)), 21) == "Replaced by v4 (1 more sub)."
    )
    assert (
        _superseded_reason(m, cast(Any, SimpleNamespace(sub_count=25)), 21)
        == "Replaced by v4 (4 fewer subs)."
    )
    assert _superseded_reason(m, cast(Any, SimpleNamespace(sub_count=21)), 21) == "Replaced by v4."


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"site_lat": 91}, "Latitude must be between −90 and 90 degrees."),
        ({"worker_count": 0}, "Workers must be between 1 and 16."),
        ({"siril_heavy_slots": 5, "worker_count": 8}, "Stacking slots must be 1–4."),
        ({"work_budget_gb": 1}, "Work budget must be 5 GB–20 TB."),
    ],
)
def test_installation_ranges(data, message):
    with pytest.raises(ApiError) as e:
        _check_installation(data, cast(Any, SimpleNamespace(worker_count=4)))
    assert message in str(e.value.detail if hasattr(e.value, "detail") else e.value)


def test_installation_values_in_range_pass():
    _check_installation(
        {"site_lat": 55, "stack_threads": 8, "siril_heavy_slots": 2},
        cast(Any, SimpleNamespace(worker_count=4)),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"grading": {"fwhm": [1.5, 1.2]}},  # reject below down-weight
        {"grading": {"stars": [0.5, 0.7]}},  # reject above down-weight for a below-is-bad measure
        {"stacking": {"sigma": [3, 11]}},
        {"stacking": {"auto_every_n": 2}},
        {"calibration": {"temp_tolerance_c": 0.1}},
        {"stacking": {"reference": "random"}},
        {"backup": {"colour": "blue"}},
    ],
)
def test_processing_changes_refused(change):
    with pytest.raises(ApiError):
        _clean_processing(change)


def test_processing_changes_accepted():
    change = {"grading": {"fwhm": [1.2, 1.5]}, "stacking": {"sigma": [3, 3], "auto_every_n": 10}}
    assert _clean_processing(change) == change


def test_outcomes_read_as_sentences():
    assert outcome("integrate", {"subs": 1200}, "M 42") == "Stacked 1,200 subs · M 42"
    assert outcome("build_master", {"result": "blocked"}, "set 3") == "Master blocked · set 3"
    assert outcome("reresolve_targets", {"datasets": 2}, "") == "Regrouped 2 datasets"
    assert (
        outcome("catalogue_frame", {"frame_type": "master_dark"}, "a.fit")
        == "Catalogued a.fit as master dark"
    )
    assert outcome("something_new", None, "") == "Something new"
