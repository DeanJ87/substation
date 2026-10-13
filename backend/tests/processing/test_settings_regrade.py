"""Settings → Grading (spec 008, 008-DR-03/04): validated thresholds, a preview of what a change would re-grade,
and "Save and re-grade" that keeps human verdicts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import (
    Dataset,
    Frame,
    FrameStatus,
    FrameType,
    Night,
    UserVerdict,
    Verdict,
    VerdictSource,
)
from apps.processing.grading import grade_session, regrade_datasets
from apps.processing.models import MachineGrade, SubMeasurement
from substation.tasks.models import Task

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 6, 21, 0, tzinfo=UTC)


def session() -> Dataset:
    ds = Dataset.objects.create(group_key="g", target="M 31", filter_norm="L", display_name="M 31 · L")
    night = Night.objects.create(site_key="x", date=T.date())
    for i, fwhm in enumerate([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.7]):  # the last is 35% above the median
        f = Frame.objects.create(
            sha256=f"{i}".rjust(64, "c"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
            dataset=ds,
            night=night,
            date_obs_utc=T,
            exptime_s=60,
        )
        SubMeasurement.objects.create(
            frame=f, state="done", stars=1000, fwhm_px=fwhm, background=100, eccentricity=0.3, roundness=0.95
        )
    grade_session(ds.pk, night.pk)
    return ds


def test_thresholds_are_validated(admin_client):
    bad = admin_client.patch(
        "/api/v1/settings", {"processing": {"grading": {"fwhm": [1.5, 1.2]}}}, content_type="application/json"
    )
    assert bad.status_code == 422 and "reject level must be" in bad.json()["message"]
    assert (
        admin_client.patch(
            "/api/v1/settings", {"processing": {"equipment": {}}}, content_type="application/json"
        ).status_code
        == 422
    )
    ok = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"stacking": {"weighting": "snr"}}},
        content_type="application/json",
    )
    assert ok.status_code == 200 and ok.json()["processing"]["stacking"]["weighting"] == "snr"


def test_preview_then_save_and_regrade_keeps_overrides(admin_client):
    ds = session()
    worst = Frame.objects.get(sha256="6".rjust(64, "c"))
    assert MachineGrade.objects.get(frame=worst).verdict == "down"  # 1.35× is past the 1.20 down-weight
    UserVerdict.objects.create(frame=worst, verdict=Verdict.ACCEPT, source=VerdictSource.OVERRIDE)
    change = {"grading": {"fwhm": [1.40, 1.60]}}
    r = admin_client.post("/api/v1/settings/preview", {"processing": change}, content_type="application/json")
    assert r.json() == [
        {"dataset_id": ds.pk, "dataset": "M 31 · L", "changes": 1, "by_change": {"down→accept": 1}}
    ]
    admin_client.patch(
        "/api/v1/settings", {"processing": change, "regrade": True}, content_type="application/json"
    )
    job = Task.objects.get(name__endswith="regrade_datasets")
    assert job.args == [[ds.pk]]
    regrade_datasets.call(*job.args)
    assert MachineGrade.objects.get(frame=worst).verdict == "accept"
    assert MachineGrade.objects.get(frame=worst).thresholds_version == 2
    assert UserVerdict.objects.filter(frame=worst).count() == 1  # the person's decision stays


def test_dataset_regrade_previews_then_queues(admin_client):
    """Re-grade on a dataset (003-DR-02): says what would change before anything does."""
    ds = session()
    admin_client.patch(
        "/api/v1/settings",
        {"processing": {"grading": {"fwhm": [1.40, 1.60]}}},
        content_type="application/json",
    )  # saved without re-grading
    r = admin_client.post(f"/api/v1/datasets/{ds.pk}/regrade", {}, content_type="application/json").json()
    assert r == {"changes": 1, "by_change": {"down→accept": 1}, "queued": False}
    assert not Task.objects.filter(name__endswith="regrade_datasets").exists()
    r = admin_client.post(
        f"/api/v1/datasets/{ds.pk}/regrade", {"confirm": True}, content_type="application/json"
    )
    assert r.json()["queued"] and Task.objects.get(name__endswith="regrade_datasets").args == [[ds.pk]]


def test_each_exposure_is_graded_against_its_own():
    """A DSLR session mixing 5 s and 300 s subs: the short ones have far fewer stars but aren't cloud."""
    ds = Dataset.objects.create(group_key="g9", target="M 31", filter_norm="OSC", display_name="M 31 · OSC")
    night = Night.objects.create(site_key="y", date=T.date())
    frames = []
    for i in range(12):
        long = i < 6
        f = Frame.objects.create(
            sha256=f"e{i}".rjust(64, "d"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
            dataset=ds,
            night=night,
            date_obs_utc=T,
            exptime_s=300 if long else 5,
        )
        SubMeasurement.objects.create(
            frame=f,
            state="done",
            stars=1500 if long else 120,
            fwhm_px=2.0,
            background=900 if long else 40,
            eccentricity=0.3,
            roundness=0.95,
        )
        frames.append(f)
    grade_session(ds.pk, night.pk)
    assert {MachineGrade.objects.get(frame=f).verdict for f in frames} == {"accept"}


def test_calibration_matching_changes_rematch(admin_client):
    """002 C17: the fallbacks are settings; changing them re-checks every light's match."""
    assert (
        admin_client.patch(
            "/api/v1/settings",
            {"processing": {"calibration": {"temp_tolerance_c": 50}}},
            content_type="application/json",
        ).status_code
        == 422
    )
    r = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"calibration": {"later_flat_fallback": True}}},
        content_type="application/json",
    )
    assert r.json()["processing"]["calibration"]["later_flat_fallback"] is True
    assert Task.objects.filter(name__endswith="rematch_lights").exists()
