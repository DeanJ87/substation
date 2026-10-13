"""The Review badge counts exactly the subs the Review page lists (spec 003 A2), without building them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, UserVerdict, Verdict, VerdictSource
from apps.processing.models import MachineGrade

pytestmark = pytest.mark.django_db
T = datetime(2026, 9, 28, 21, 0, tzinfo=UTC)


def test_review_count_matches_review(admin_client):
    ds = Dataset.objects.create(group_key="g", target="M 31", filter_norm="L", display_name="M 31")
    cases = [
        ("accept", False, None),
        ("accept", True, None),
        ("down", False, None),
        ("reject", False, None),
        ("reject", False, Verdict.ACCEPT),
        ("accept", True, Verdict.AUTO),
        ("down", False, "nina"),
    ]
    for i, (verdict, near, human) in enumerate(cases):
        f = Frame.objects.create(
            sha256=f"{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
            dataset=ds,
            date_obs_utc=T,
            exptime_s=60,
        )
        MachineGrade.objects.create(frame=f, verdict=verdict, reason="r", near_threshold=near)
        if human == "nina":
            UserVerdict.objects.create(frame=f, verdict=Verdict.REJECT, source=VerdictSource.NINA_BAD_PREFIX)
        elif human:
            UserVerdict.objects.create(frame=f, verdict=human, source=VerdictSource.OVERRIDE)
    listed = sum(len(g["subs"]) for g in admin_client.get("/api/v1/review").json())
    assert listed == 4  # near, down, reject, and the near one reverted to auto
    assert admin_client.get("/api/v1/review/count").json() == {"count": listed}


def test_a_master_takes_its_jobs_outcome():
    """A master whose job failed or was cancelled outside it never shows "integrating" for ever (004 T002)."""
    from django.utils import timezone

    from apps.processing.masters import reconcile_states
    from apps.processing.models import Master
    from substation.tasks.models import Task, TaskStatus

    ds = Dataset.objects.create(group_key="g2", target="M 31", filter_norm="L", display_name="M 31")
    now = timezone.now()
    jobs = [
        Task.objects.create(
            name="apps.processing.masters.integrate",
            status=s,
            run_after=now,
            enqueued_at=now,
            error="Traceback\nRuntimeError: worker lost" if s == TaskStatus.FAILED else None,
        )
        for s in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.RUNNING)
    ]
    ms = [
        Master.objects.create(dataset=ds, version=i + 1, state="running", task=j) for i, j in enumerate(jobs)
    ]
    assert reconcile_states() == 2
    states = [Master.objects.get(pk=m.pk) for m in ms]
    assert states[0].state == "failed" and states[0].error == "RuntimeError: worker lost"
    assert states[1].state == "cancelled" and states[2].state == "running"


def test_deleting_a_master_keeps_the_record(admin_client, tmp_path):
    """004 T001 (constitution VIII): the file goes, the row records who deleted it and when, and lists hide it."""
    from apps.processing.models import Master

    ds = Dataset.objects.create(group_key="g3", target="M 31", filter_norm="L", display_name="M 31")
    out = tmp_path / "master_v1.fit"
    out.write_bytes(b"x")
    m = Master.objects.create(dataset=ds, version=1, state="current", output_path=str(out))
    assert admin_client.delete(f"/api/v1/stacks/{m.pk}").status_code == 204
    m.refresh_from_db()
    assert m.state == "deleted" and m.deleted_by.username == "admin" and m.deleted_at and not out.exists()
    assert admin_client.get(f"/api/v1/datasets/{ds.pk}/stacks").json() == []


def test_a_master_can_override_stacking_options(admin_client, monkeypatch):
    """004 T016: options sent with a stack apply to that master only, on top of the Settings defaults."""
    from apps.processing import masters

    seen = {}

    def fake_start(ds, nights, rule, user=None, options=None, scope=None):
        seen["options"] = options
        raise ValueError("stop here")

    monkeypatch.setattr(masters, "start", fake_start)
    ds = Dataset.objects.create(group_key="g4", target="M 31", filter_norm="L", display_name="M 31")
    r = admin_client.post(
        f"/api/v1/datasets/{ds.pk}/stacks",
        {"rule": "default", "options": {"weighting": "snr"}},
        content_type="application/json",
    )
    assert r.status_code == 422 and seen["options"] == {"weighting": "snr"}
    bad = admin_client.post(
        f"/api/v1/datasets/{ds.pk}/stacks",
        {"options": {"weighting": "loud"}},
        content_type="application/json",
    )
    assert bad.status_code == 422


def test_retiring_a_master_rematches(admin_client):
    """002 C13: retiring is an ignore rule on the master's content; lights are matched again."""
    from substation.tasks.models import Task

    f = Frame.objects.create(
        sha256="ab" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_DARK,
    )
    r = admin_client.post(
        "/api/v1/ignore-rules",
        {"kind": "content", "value": f.sha256, "note": "Retired master"},
        content_type="application/json",
    )
    assert r.status_code == 201
    assert Task.objects.filter(name__endswith="rematch_lights").exists()


def test_newer_calibration_is_offered_not_applied(admin_client):
    """002 C11 / 004 T014: a measured sub whose match now names another master is listed, and only re-measured
    (its stacks marked stale) when asked."""
    from apps.processing.models import CalibrationMatch, Master, MasterMember, SubMeasurement
    from substation.tasks.models import Task

    ds = Dataset.objects.create(group_key="g5", target="M 31", filter_norm="L", display_name="M 31")
    old = Frame.objects.create(
        sha256="d1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_DARK,
    )
    new = Frame.objects.create(
        sha256="d2" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_DARK,
    )
    sub = Frame.objects.create(
        sha256="s1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        dataset=ds,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
    )
    SubMeasurement.objects.create(frame=sub, state="done", dark=old)
    CalibrationMatch.objects.create(frame=sub, state="matched", dark=new)
    m = Master.objects.create(dataset=ds, version=1, state="current")
    MasterMember.objects.create(master=m, frame=sub, included=True)
    assert admin_client.get(f"/api/v1/datasets/{ds.pk}/recalibration").json()["pending"] == 1
    assert not Task.objects.filter(name__endswith="calibrate_measure").exists()
    r = admin_client.post(f"/api/v1/datasets/{ds.pk}/recalibration").json()
    assert r["queued"] == 1 and Task.objects.filter(name__endswith="calibrate_measure").exists()
    m.refresh_from_db()
    assert m.state == "stale" and "Calibration changed" in m.state_reason


def test_a_session_can_use_other_masters(admin_client):
    """002 C10: pick another dark or flat for one session; the choice is pinned and the session re-measured."""
    from datetime import date

    from apps.catalogue.models import Night
    from apps.processing.matching import update_match
    from apps.processing.models import CalibrationMatch
    from substation.tasks.models import Task

    night = Night.objects.create(site_key="z", date=date(2026, 3, 6))
    ds = Dataset.objects.create(group_key="g6", target="M 31", filter_norm="Hα", display_name="M 31")
    sub = Frame.objects.create(
        sha256="c3" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        dataset=ds,
        night=night,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        camera="ATR2600M",
        exptime_s=600,
        filter_norm="Hα",
    )
    dark = Frame.objects.create(
        sha256="d3" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        camera="ATR2600M",
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_DARK,
        exptime_s=600,
    )
    choices = admin_client.get(f"/api/v1/datasets/{ds.pk}/sessions/2026-03-06/calibration").json()
    assert [d["sha256"] for d in choices["darks"]] == [dark.pk]
    r = admin_client.post(
        f"/api/v1/datasets/{ds.pk}/sessions/2026-03-06/calibration",
        {"dark": dark.pk},
        content_type="application/json",
    )
    assert r.json()["queued"] == 1 and Task.objects.filter(name__endswith="calibrate_measure").exists()
    cm = CalibrationMatch.objects.get(frame=sub)
    assert cm.pinned and cm.dark_id == dark.pk and cm.dark_note == "Chosen by you"
    assert update_match(sub).dark_id == dark.pk  # a rematch keeps the choice
