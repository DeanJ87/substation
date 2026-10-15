"""Spec 016: agree with a night's grades in one go, and undo verdicts, agreements and binning."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Change, Dataset, Frame, FrameStatus, Night, UserVerdict
from apps.processing.models import MachineGrade
from tests.unit.test_binning import sub

pytestmark = pytest.mark.django_db
T = datetime(2026, 10, 11, 22, tzinfo=UTC)


def _graded(tmp_path, grades: list[tuple[str, bool]]) -> tuple[Dataset, list[Frame]]:
    d = Dataset.objects.create(
        group_key="ngc7000", target="NGC 7000", filter_norm="OIII", display_name="NGC 7000"
    )
    night = Night.objects.create(site_key="55.0,-1.7", date=date(2026, 10, 11))
    out = []
    for i, (verdict, near) in enumerate(grades):
        f, _ = sub(tmp_path, f"s{i}.fits")
        Frame.objects.filter(pk=f.pk).update(dataset=d, night=night, date_obs_utc=T)
        MachineGrade.objects.create(frame=f, verdict=verdict, reason="r", near_threshold=near, weight=0.6)
        out.append(f)
    return d, out


def _review(client) -> int:
    return sum(len(g["subs"]) for g in client.get("/api/v1/review").json())


def test_agreeing_takes_a_nights_flagged_subs_off_the_list_and_undo_puts_them_back(tmp_path, admin_client):
    d, fs = _graded(tmp_path, [("reject", False), ("down", False), ("accept", True), ("accept", False)])
    assert _review(admin_client) == 3
    r = admin_client.post(
        "/api/v1/frames/agree", {"dataset_id": d.pk, "night": "2026-10-11"}, content_type="application/json"
    ).json()
    assert r["updated"] == 3 and r["change_id"]
    assert _review(admin_client) == 0
    kept = {v.frame_id: v.verdict for v in UserVerdict.objects.all()}
    assert kept == {fs[0].pk: "reject", fs[1].pk: "keep", fs[2].pk: "accept"}  # the grade, as your verdict
    changes = admin_client.get("/api/v1/changes").json()
    assert changes[0]["summary"] == "Agreed with 3 grades · NGC 7000 · 11 Oct 2026" and changes[0]["can_undo"]
    u = admin_client.post(f"/api/v1/changes/{r['change_id']}/undo")
    assert u.status_code == 200 and u.json()["note"].startswith("Undone: agreed with 3 grades")
    assert not UserVerdict.objects.exists() and _review(admin_client) == 3
    again = admin_client.post(f"/api/v1/changes/{r['change_id']}/undo")
    assert again.status_code == 409 and "already undone" in again.json()["message"]


def test_undoing_a_verdict_leaves_later_ones(tmp_path, admin_client):
    _, fs = _graded(tmp_path, [("accept", False), ("accept", False)])
    first = admin_client.post(
        "/api/v1/frames/verdict",
        {"sha256s": [f.pk for f in fs], "verdict": "reject"},
        content_type="application/json",
    ).json()
    admin_client.post(
        "/api/v1/frames/verdict",
        {"sha256s": [fs[0].pk], "verdict": "accept"},
        content_type="application/json",
    )
    admin_client.post(f"/api/v1/changes/{first['change_id']}/undo")
    assert list(UserVerdict.objects.values_list("frame_id", "verdict")) == [(fs[0].pk, "accept")]
    assert Change.objects.get(pk=first["change_id"]).summary == "Rejected 2 subs"


def test_binning_is_undone_by_restoring(tmp_path, admin_client):
    _, fs = _graded(tmp_path, [("reject", False)])
    r = admin_client.post("/api/v1/bin", {"sha256s": [fs[0].pk]}, content_type="application/json").json()
    assert r["binned"] == 1 and r["change_id"]
    admin_client.post(f"/api/v1/changes/{r['change_id']}/undo")
    fs[0].refresh_from_db()
    assert fs[0].status == FrameStatus.CATALOGUED  # out of the bin (its type is read again from the file)


def test_only_the_maker_or_an_admin_undoes(tmp_path, admin_client, standard_client):
    _, fs = _graded(tmp_path, [("accept", False)])
    c = admin_client.post(
        "/api/v1/frames/verdict",
        {"sha256s": [fs[0].pk], "verdict": "reject"},
        content_type="application/json",
    ).json()["change_id"]
    assert standard_client.get("/api/v1/changes").json() == []  # yours only
    assert standard_client.post(f"/api/v1/changes/{c}/undo").status_code == 403


def test_collection_goals_are_set_changed_and_removed(admin_client):
    """Spec 019: hours wanted per filter."""
    from apps.catalogue.models import Collection

    col = Collection.objects.create(name="M 81")
    url = f"/api/v1/collections/{col.pk}"
    r = admin_client.patch(url, {"goals": {"L": 10, "Ha": 20}}, content_type="application/json").json()
    assert r["goals"] == {"L": 10, "Ha": 20}
    r = admin_client.patch(url, {"goals": {"L": 0, "R": 2.5}}, content_type="application/json").json()
    assert r["goals"] == {"Ha": 20, "R": 2.5}
    bad = admin_client.patch(url, {"goals": {"OIII": 5000}}, content_type="application/json")
    assert bad.status_code == 422 and "1,000 hours" in bad.json()["message"]
