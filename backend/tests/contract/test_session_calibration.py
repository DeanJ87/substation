"""Owner 2026-10-10: choose a flat set (built on demand) for a session, and say which filter a session used."""

import json
from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import CalibrationSet, Dataset, Frame, FrameStatus, FrameType, MetadataValue, Night
from apps.processing.models import BuiltMaster, CalibrationMatch
from substation.tasks.models import Task

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 6, 21, 0, tzinfo=UTC)


def _session():
    night = Night.objects.create(site_key="z", date=date(2026, 3, 6))
    ds = Dataset.objects.create(group_key="g7", target="M 31", filter_norm="OSC", display_name="M 31")
    sub = Frame.objects.create(
        sha256="e1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        dataset=ds,
        night=night,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        camera="A7 III",
        exptime_s=300,
        filter_norm="OSC",
    )
    return ds, sub


def test_a_flat_set_is_offered_and_built_when_chosen(admin_client):
    from apps.processing.calibration import _apply_chosen

    ds, sub = _session()
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT,
        camera="A7 III",
        filter_norm="Duo NB",
        exptime_s=0.1,
        session_start_utc=datetime(2026, 3, 8, 6, tzinfo=UTC),
        session_end_utc=datetime(2026, 3, 8, 7, tzinfo=UTC),
        frame_count=30,
    )
    Frame.objects.create(
        sha256="f1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        calibration_set=cs,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.FLAT,
        camera="A7 III",
    )
    url = f"/api/v1/datasets/{ds.pk}/sessions/2026-03-06/calibration"
    choices = admin_client.get(url).json()
    assert [c["set_id"] for c in choices["flat_sets"]] == [cs.pk]
    note = choices["flat_sets"][0]["note"]
    assert "1 day after" in note and "filter Duo NB, not OSC" in note and "OSC" in choices["filters"]
    r = admin_client.post(url, json.dumps({"flat_set": cs.pk}), content_type="application/json")
    assert r.status_code == 200
    cm = CalibrationMatch.objects.get(frame=sub)
    assert (
        cm.pending_flat_set_id == cs.pk
        and cm.pinned
        and Task.objects.filter(name__endswith="build_master").exists()
    )
    master = Frame.objects.create(
        sha256="m1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        camera="A7 III",
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_FLAT,
    )
    BuiltMaster.objects.filter(calibration_set=cs).update(state="done", frame=master)
    assert _apply_chosen(cs) == 1
    cm.refresh_from_db()
    assert cm.flat_id == master.pk and cm.pending_flat_set_id is None and cm.flat_note == "Chosen by you"


def test_a_whole_session_can_be_given_another_filter(admin_client):
    ds, sub = _session()
    r = admin_client.post(
        f"/api/v1/datasets/{ds.pk}/sessions/2026-03-06/filter",
        json.dumps({"filter": "Duo NB"}),
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["updated"] == 1
    sub.refresh_from_db()
    assert sub.filter_norm == "Duo NB" and sub.dataset_id == r.json()["dataset_id"] != ds.pk


def test_datasets_with_newer_calibration_are_listed(admin_client):
    """002 C11: a calibrated sub whose match now names another master is listed, never re-calibrated silently."""
    from apps.processing.models import MatchState, SubMeasurement

    ds, sub = _session()
    old = Frame.objects.create(
        sha256="o1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        camera="A7 III",
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_FLAT,
    )
    new = Frame.objects.create(
        sha256="n1" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        camera="A7 III",
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.MASTER_FLAT,
    )
    SubMeasurement.objects.create(frame=sub, state="done", flat=old)
    CalibrationMatch.objects.create(frame=sub, state=MatchState.MATCHED, flat=old)
    assert admin_client.get("/api/v1/calibration/recalibration").json() == []
    CalibrationMatch.objects.filter(frame=sub).update(flat=new)
    rows = admin_client.get("/api/v1/calibration/recalibration").json()
    assert [(r["dataset_id"], r["subs"], r["sessions"]) for r in rows] == [(ds.pk, 1, 1)]


def test_a_flat_set_can_be_given_its_filter(admin_client):
    """A camera with no filter wheel records none: flats shot through a Duo NB read as OSC until told."""
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT,
        camera="A7 III",
        filter_norm="OSC",
        exptime_s=0.1,
        session_start_utc=datetime(2026, 3, 7, 5, tzinfo=UTC),
        session_end_utc=datetime(2026, 3, 7, 6, tzinfo=UTC),
        frame_count=1,
    )
    flat = Frame.objects.create(
        sha256="f2" * 32,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        date_obs_utc=datetime(2026, 3, 7, 5, 30, tzinfo=UTC),
        calibration_set=cs,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.FLAT,
        camera="A7 III",
        exptime_s=0.1,
        filter_norm="OSC",
    )
    for field, value in (
        ("frame_type", "flat"),
        ("camera", "A7 III"),
        ("exptime", "0.1"),
        ("date_obs", "2026-03-07T05:30:00+00:00"),
    ):
        MetadataValue.objects.create(
            frame=flat, field=field, value=value, raw=value, source="header", is_winner=True
        )
    r = admin_client.post(
        f"/api/v1/calibration-sets/{cs.pk}/filter",
        json.dumps({"filter": "Duo NB"}),
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["updated"] == 1
    flat.refresh_from_db()
    assert flat.filter_norm == "Duo NB"
    assert flat.calibration_set is not None and flat.calibration_set.filter_norm == "Duo NB"
    dark = CalibrationSet.objects.create(
        type=FrameType.DARK,
        camera="A7 III",
        exptime_s=300,
        frame_count=0,
        session_start_utc=datetime(2026, 3, 7, 5, tzinfo=UTC),
        session_end_utc=datetime(2026, 3, 7, 6, tzinfo=UTC),
    )
    r = admin_client.post(
        f"/api/v1/calibration-sets/{dark.pk}/filter",
        json.dumps({"filter": "Duo NB"}),
        content_type="application/json",
    )
    assert r.status_code == 422
