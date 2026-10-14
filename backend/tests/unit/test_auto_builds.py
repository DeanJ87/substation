"""002-DR-23: masters are built from settled calibration sessions, and a blocked flat is retried once a bias that
could unblock it has been built."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.catalogue.models import CalibrationSet, Frame
from apps.processing.calibration import auto_builds
from apps.processing.models import BuiltMaster

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)


def _set(kind: str, seen_minutes_ago: float, n: int = 3, offset: int = 50) -> CalibrationSet:
    cs = CalibrationSet.objects.create(
        type=kind,
        camera="ATR2600M",
        exptime_s=1.0,
        gain=100,
        offset=offset,
        session_start_utc=NOW - timedelta(hours=1),
        session_end_utc=NOW,
        frame_count=n,
    )
    for i in range(n):
        Frame.objects.create(
            sha256=f"{cs.pk:08x}{i:056x}",
            size_bytes=1,
            format="fits",
            status="catalogued",
            frame_type=kind,
            first_seen_at=NOW - timedelta(minutes=seen_minutes_ago),
            calibration_set=cs,
        )
    return cs


def test_a_settled_session_is_built_and_one_still_arriving_waits(monkeypatch):
    monkeypatch.setattr("apps.processing.calibration.enqueue", lambda *a, **k: None)
    settled, arriving, small = _set("dark", 60), _set("dark", 5), _set("dark", 60, n=2)
    assert auto_builds(now=NOW) == [settled.pk]
    assert auto_builds(now=NOW) == []  # queued now: not again
    assert not BuiltMaster.objects.filter(calibration_set__in=[arriving, small]).exists()


def test_a_blocked_flat_is_retried_once_a_matching_bias_is_built(monkeypatch):
    monkeypatch.setattr("apps.processing.calibration.enqueue", lambda *a, **k: None)
    flat, bias = _set("flat", 60), _set("bias", 60)
    other_bias = _set("bias", 60, offset=60)
    blocked = BuiltMaster.objects.create(
        calibration_set=flat, state="blocked", finished_at=NOW - timedelta(hours=2)
    )
    BuiltMaster.objects.create(calibration_set=bias, state="done", finished_at=NOW - timedelta(hours=3))
    BuiltMaster.objects.create(
        calibration_set=other_bias, state="done", finished_at=NOW - timedelta(minutes=30)
    )
    assert flat.pk not in auto_builds(now=NOW)  # only a bias at another offset was built since
    BuiltMaster.objects.filter(calibration_set=bias).update(finished_at=NOW - timedelta(minutes=10))
    assert flat.pk in auto_builds(now=NOW)
    assert BuiltMaster.objects.filter(calibration_set=flat).exclude(pk=blocked.pk).get().state == "queued"
