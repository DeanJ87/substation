"""002-DR-26: the dark picker says how each master differs from the session's subs, lists those that fit first, and
a session can go back to automatic; a sub calibrated with a dark it no longer uses loses that calibration."""

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, Night
from apps.processing.models import CalibrationMatch, MatchState, SubMeasurement

pytestmark = pytest.mark.django_db
T = datetime(2026, 1, 22, 21, 0, tzinfo=UTC)
URL = "/api/v1/datasets/{}/sessions/2026-01-22/calibration"


def _frame(sha, **kw):
    return Frame.objects.create(
        sha256=sha * 32, size_bytes=1, format="fits", first_seen_at=T, status=FrameStatus.CATALOGUED, **kw
    )


def _setup():
    night = Night.objects.create(site_key="z", date=date(2026, 1, 22))
    ds = Dataset.objects.create(group_key="m42g", target="M 42", filter_norm="G", display_name="M 42 · G")
    sub = _frame(
        "a1",
        dataset=ds,
        night=night,
        frame_type=FrameType.LIGHT,
        camera="ATR2600M",
        exptime_s=120,
        gain=100,
        offset=50,
        ccd_temp_c=-1.0,
        filter_norm="G",
    )
    wrong = _frame(
        "b2",
        frame_type=FrameType.MASTER_DARK,
        camera="ATR2600M",
        exptime_s=120,
        gain=120,
        offset=80,
        set_temp_c=-20.0,
    )
    right = _frame(
        "c3",
        frame_type=FrameType.MASTER_DARK,
        camera="ATR2600M",
        exptime_s=120,
        gain=100,
        offset=50,
        set_temp_c=0.0,
    )
    return ds, sub, wrong, right


def test_mismatches_are_spelled_out_and_fitting_darks_come_first(admin_client):
    ds, _sub, wrong, right = _setup()
    darks = admin_client.get(URL.format(ds.pk)).json()["darks"]
    assert darks[0]["sha256"] == right.pk and darks[0]["mismatch"] == []
    bad = next(d for d in darks if d["sha256"] == wrong.pk)
    assert "gain 120, the subs are 100" in bad["mismatch"] and "offset 80, the subs are 50" in bad["mismatch"]
    assert any("−20" in m or "-20" in m for m in bad["mismatch"])
    assert "gain 120" in bad["note"] and "offset 80" in bad["note"]


def test_back_to_automatic_drops_a_calibration_made_with_the_wrong_dark(admin_client):
    ds, sub, wrong, right = _setup()
    admin_client.post(URL.format(ds.pk), {"dark": wrong.pk}, content_type="application/json")
    SubMeasurement.objects.update_or_create(frame=sub, defaults={"state": "done", "dark": wrong})
    right.status = FrameStatus.IGNORED  # tonight's dark isn't built yet
    right.save(update_fields=["status"])
    r = admin_client.post(URL.format(ds.pk), {"automatic": True}, content_type="application/json").json()
    cm = CalibrationMatch.objects.get(frame=sub)
    assert not cm.pinned and cm.state == MatchState.AWAITING and r["pending"] == 1
    assert not SubMeasurement.objects.filter(frame=sub).exists()  # nothing stacked or judged from it


def test_a_flat_chosen_with_no_matching_dark_waits_for_one(admin_client):
    """M 42 · B, 2026-10-14: a flat chosen for a session with no dark calibrated 41 subs without one."""
    from apps.processing.matching import update_match
    from substation.tasks.models import Task

    ds, sub, wrong, right = _setup()
    right.status = FrameStatus.IGNORED
    right.save(update_fields=["status"])
    flat = _frame("d4", frame_type=FrameType.MASTER_FLAT, camera="ATR2600M", filter_norm="G")
    r = admin_client.post(URL.format(ds.pk), {"flat": flat.pk}, content_type="application/json").json()
    cm = CalibrationMatch.objects.get(frame=sub)
    assert (
        r["queued"] == 0 and r["pending"] == 1 and cm.state == MatchState.AWAITING and cm.flat_id == flat.pk
    )
    assert "120 s dark" in cm.reason and not Task.objects.filter(name__endswith="calibrate_measure").exists()
    right.status = FrameStatus.CATALOGUED  # tonight's dark arrives
    right.save(update_fields=["status"])
    again = update_match(sub)
    assert again is not None and again.state == MatchState.MATCHED
    assert again.dark_id == right.pk and again.flat_id == flat.pk


def test_recalibration_says_what_changes_and_why(admin_client):
    """002-DR-28: newer calibration is offered with what it changes, so it can be judged."""
    ds, sub, wrong, right = _setup()
    SubMeasurement.objects.update_or_create(frame=sub, defaults={"state": "done", "dark": wrong})
    flat = _frame("e5", frame_type=FrameType.MASTER_FLAT, camera="ATR2600M", filter_norm="G")
    CalibrationMatch.objects.update_or_create(
        frame=sub, defaults={"state": MatchState.MATCHED, "dark": right, "flat": None}
    )
    SubMeasurement.objects.filter(frame=sub).update(flat=flat)
    r = admin_client.get(f"/api/v1/datasets/{ds.pk}/recalibration").json()
    (c,) = r["changes"]
    assert c["subs"] == 1 and c["night"] == "2026-01-22"
    assert "0 °C instead of -20 °C" in " ".join(c["why"])
    assert c["flat_from"] and c["flat_to"] is None
