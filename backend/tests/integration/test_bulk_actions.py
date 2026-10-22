"""Spec 016 U6: bulk actions beyond subs. Build several calibration sets, override QA on several frames, re-grade,
stack or move several datasets, retry or dismiss several failed jobs; moving, dismissing and QA overrides undo."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.catalogue.models import CalibrationSet, Change, Collection, Dataset, Frame, Project
from apps.processing.models import BuiltMaster, CalibrationQA
from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)


def post(client, url: str, body: dict):
    return client.post(f"/api/v1{url}", data=json.dumps(body), content_type="application/json")


def undo(client, change_id: int):
    r = client.post(f"/api/v1/changes/{change_id}/undo")
    assert r.status_code == 200, r.content
    return r.json()["note"]


@pytest.fixture
def viewer_client(db, django_user_model):
    from django.contrib.auth.models import Group

    from apps.accounts.roles import VIEWER, ensure_groups
    from tests.conftest import signed_in_client

    ensure_groups()
    u = django_user_model.objects.create_user(username="guest", password="correct-horse-battery")
    u.groups.add(Group.objects.get(name=VIEWER))
    return signed_in_client("guest")


def _set(kind: str = "dark", n: int = 3) -> CalibrationSet:
    cs = CalibrationSet.objects.create(
        type=kind,
        camera="ATR2600M",
        exptime_s=1.0,
        gain=100,
        offset=50,
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
            first_seen_at=NOW,
            calibration_set=cs,
        )
    return cs


def test_several_calibration_sets_build_at_once_and_one_already_building_is_skipped(
    monkeypatch, admin_client
):
    monkeypatch.setattr("apps.processing.calibration.enqueue", lambda *a, **k: None)
    a, b, busy = _set(), _set("flat"), _set("bias")
    BuiltMaster.objects.create(calibration_set=busy, state="queued", method="")
    r = post(admin_client, "/bulk/calibration-sets/build", {"ids": [a.pk, b.pk, busy.pk]}).json()
    assert r["queued"] == 2
    assert r["skipped"] == [{"id": busy.pk, "reason": "Already building."}]
    assert BuiltMaster.objects.filter(calibration_set__in=[a, b], state="queued").count() == 2


def test_overriding_qa_on_several_frames_is_undone_unless_changed_again(admin_client):
    cs = _set("flat")
    shas = list(Frame.objects.filter(calibration_set=cs).values_list("sha256", flat=True))
    for sha in shas:
        CalibrationQA.objects.create(frame_id=sha, verdict="pass", override="")
    CalibrationQA.objects.filter(frame_id=shas[2]).update(override="pass")
    r = post(admin_client, "/calibration-qa/override", {"sha256s": shas, "verdict": "reject"}).json()
    assert r["queued"] == 3 and r["change_id"]
    assert Change.objects.get(pk=r["change_id"]).summary == "Left out 3 calibration frames"
    post(admin_client, "/calibration-qa/override", {"sha256s": [shas[1]], "verdict": None})  # changed again
    assert undo(admin_client, r["change_id"]) == "Put back the QA choice on 2 frames."
    assert dict(CalibrationQA.objects.values_list("frame_id", "override")) == {
        shas[0]: "",
        shas[1]: "",  # your later choice stays
        shas[2]: "pass",
    }
    nothing = post(admin_client, "/calibration-qa/override", {"sha256s": [shas[2]], "verdict": "pass"}).json()
    assert nothing == {"queued": 0, "change_id": None}


def _ds(name: str, col: Collection | None = None, project: Project | None = None) -> Dataset:
    return Dataset.objects.create(
        group_key=name, target=name, display_name=name, collection=col, project=project, project_position=1
    )


def test_moving_datasets_records_where_they_were_and_undo_puts_them_back(admin_client):
    soul, heart = Collection.objects.create(name="Soul"), Collection.objects.create(name="Heart")
    mosaic = Project.objects.create(collection=soul, own_name="Mosaic 2026")
    a, b, c = _ds("IC 1848", soul, mosaic), _ds("IC 1805", heart), _ds("NGC 896")
    r = post(
        admin_client, "/bulk/datasets/move", {"dataset_ids": [a.pk, b.pk, c.pk], "collection_id": heart.pk}
    )
    assert r.json()["moved"] == 2  # b is in Heart already
    assert set(heart.datasets.values_list("pk", flat=True)) == {a.pk, b.pk, c.pk}
    a.refresh_from_db()
    assert a.project_id is None  # projects belong to the collection it left
    assert admin_client.get("/api/v1/changes").json()[0]["summary"] == "Moved 2 datasets to Heart"
    assert undo(admin_client, r.json()["change_id"]) == "Put 2 datasets back where they were."
    a.refresh_from_db()
    c.refresh_from_db()
    assert (a.collection_id, a.project_id, a.project_position) == (soul.pk, mosaic.pk, 1)
    assert c.collection_id is None
    assert Collection.objects.get(pk=soul.pk).objects_text == "IC 1848"


def test_taking_datasets_out_of_collections_and_a_later_move_survives_undo(admin_client):
    soul, heart = Collection.objects.create(name="Soul"), Collection.objects.create(name="Heart")
    a, b = _ds("IC 1848", soul), _ds("IC 1805", soul)
    out = post(
        admin_client, "/bulk/datasets/move", {"dataset_ids": [a.pk, b.pk], "collection_id": None}
    ).json()
    assert Change.objects.get(pk=out["change_id"]).summary == "Took 2 datasets out of their collection"
    post(admin_client, "/bulk/datasets/move", {"dataset_ids": [b.pk], "collection_id": heart.pk})
    assert undo(admin_client, out["change_id"]) == "Put 1 dataset back where it was."
    assert set(soul.datasets.values_list("pk", flat=True)) == {a.pk}
    assert set(heart.datasets.values_list("pk", flat=True)) == {b.pk}
    assert post(
        admin_client, "/bulk/datasets/move", {"dataset_ids": [b.pk], "collection_id": heart.pk}
    ).json() == {
        "moved": 0,
        "change_id": None,
    }
    assert (
        post(
            admin_client, "/bulk/datasets/move", {"dataset_ids": [a.pk], "collection_id": 999999}
        ).status_code
        == 404
    )


def test_regrading_and_stacking_several_datasets(monkeypatch, admin_client):
    jobs: list = []
    monkeypatch.setattr("apps.processing.api_bulk.enqueue", lambda fn, ids, **k: jobs.append(ids))
    a, b = _ds("M 81"), _ds("M 82")
    assert post(admin_client, "/bulk/datasets/regrade", {"dataset_ids": [b.pk, a.pk, 999999]}).json() == {
        "queued": 2
    }
    assert jobs == [[a.pk, b.pk]]  # one job for all of them

    class M:
        pk = 77

    def start(ds, nights, rule, user):  # noqa: ANN001, ANN202
        assert nights is None and rule == "default"
        if ds.pk == b.pk:
            raise ValueError("Needs at least two calibrated subs.")
        return M()

    monkeypatch.setattr("apps.processing.masters.start", start)
    r = post(admin_client, "/bulk/datasets/stack", {"dataset_ids": [a.pk, b.pk]}).json()
    assert r == {
        "started": 1,
        "master_ids": [77],
        "skipped": [{"id": b.pk, "reason": "Needs at least two calibrated subs."}],
    }


def _failed(note: str = "") -> Task:
    now = timezone.now()
    return Task.objects.create(
        name="apps.processing.tasks.calibrate_measure",
        status=TaskStatus.FAILED,
        run_after=now,
        enqueued_at=now,
        finished_at=now,
        progress_note=note,
    )


def test_failed_jobs_retry_and_dismiss_many_and_dismissing_undoes(admin_client, standard_client):
    a, b, c = _failed("half way"), _failed(), _failed()
    ok = Task.objects.create(
        name="x", status=TaskStatus.SUCCEEDED, run_after=timezone.now(), enqueued_at=timezone.now()
    )
    ids = [str(a.pk), str(b.pk), str(ok.pk), "not-a-job"]
    r = post(standard_client, "/work/bulk/jobs/dismiss", {"ids": ids}).json()
    assert r["done"] == 2 and r["change_id"]
    assert set(Task.objects.filter(progress_note="dismissed").values_list("pk", flat=True)) == {a.pk, b.pk}
    failed = [j["id"] for j in admin_client.get("/api/v1/work").json()["failed"]]
    assert failed == [str(c.pk)]
    assert undo(standard_client, r["change_id"]) == "2 failed jobs back in Activity."
    assert Task.objects.get(pk=a.pk).progress_note == "half way"
    assert (
        post(standard_client, "/work/bulk/jobs/retry", {"ids": [str(c.pk)]}).status_code == 403
    )  # admins only
    r = post(admin_client, "/work/bulk/jobs/retry", {"ids": [str(a.pk), str(c.pk), str(ok.pk)]}).json()
    assert r == {"done": 2, "change_id": None}
    assert Task.objects.get(pk=c.pk).status == TaskStatus.READY
    assert post(admin_client, "/work/bulk/jobs/dismiss", {"ids": [str(ok.pk)]}).json() == {
        "done": 0,
        "change_id": None,
    }
    assert post(admin_client, "/work/bulk/jobs/retry", {"ids": ["x"] * 501}).status_code == 422


def test_read_only_accounts_and_empty_or_huge_choices_are_refused(viewer_client, admin_client):
    for url, body in [
        ("/bulk/calibration-sets/build", {"ids": [1]}),
        ("/bulk/datasets/regrade", {"dataset_ids": [1]}),
        ("/bulk/datasets/stack", {"dataset_ids": [1]}),
        ("/bulk/datasets/move", {"dataset_ids": [1]}),
        ("/calibration-qa/override", {"sha256s": ["a"], "verdict": "pass"}),
        ("/work/bulk/jobs/dismiss", {"ids": ["a"]}),
    ]:
        assert post(viewer_client, url, body).status_code == 403, url
    assert post(admin_client, "/bulk/datasets/regrade", {"dataset_ids": []}).status_code == 422
    assert post(admin_client, "/bulk/datasets/stack", {"dataset_ids": list(range(501))}).status_code == 422


def test_undoing_a_move_after_the_old_collection_was_removed_leaves_them_unfiled(admin_client):
    """Review 2026-10-15: the collection a move came from may be gone by the time it's undone."""
    soul, heart = Collection.objects.create(name="Soul"), Collection.objects.create(name="Heart")
    mosaic = Project.objects.create(collection=soul, own_name="Mosaic 2026")
    a = _ds("IC 1848", soul, mosaic)
    r = post(admin_client, "/bulk/datasets/move", {"dataset_ids": [a.pk], "collection_id": heart.pk})
    soul.delete()  # its project goes with it
    assert undo(admin_client, r.json()["change_id"]) == "Put 1 dataset back where it was."
    a.refresh_from_db()
    assert (a.collection_id, a.project_id) == (None, None)


def test_stats_for_a_rig_name_shared_by_two_rigs_count_both(admin_client):
    """Review 2026-10-15: a rig named the older way may name several rigs (same telescope, two cameras)."""
    from apps.catalogue.models import Rig

    r1 = Rig.objects.create(key="redcat|a", name="Redcat 51", camera="A")
    r2 = Rig.objects.create(key="redcat|b", name="Redcat 51", camera="B")
    for i, rig in enumerate((r1, r2)):
        d = Dataset.objects.create(
            group_key=f"g{i}", target="M 31", filter_norm="L", display_name=f"d{i}", rig=rig
        )
        Frame.objects.create(
            sha256=f"{i:064x}",
            size_bytes=1,
            format="fits",
            first_seen_at=timezone.now(),
            status="catalogued",
            frame_type="light",
            dataset=d,
            exptime_s=3600,
        )
    stats = admin_client.get("/api/v1/library/stats?rig=Redcat%2051").json()
    assert stats["by_rig"] == {"Redcat 51": 2.0} or sum(stats["by_rig"].values()) == 2.0
