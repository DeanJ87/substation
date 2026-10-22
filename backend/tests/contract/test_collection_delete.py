"""Deleting a collection's record (amendment 2026-10-22): never the owner's files; refused while its files move or
while it has combined masters; undone with the same ids."""

import json
from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Change, Collection, CollectionMove, Dataset, Project
from apps.finished.models import FinishedProject
from apps.libraries.models import Library, LibraryRole
from apps.processing.models import CombinedMaster

pytestmark = pytest.mark.django_db
DONE = datetime(2026, 10, 1, 21, tzinfo=UTC)


def ds(col, key, project=None, position=None):
    return Dataset.objects.create(
        group_key=key,
        display_name=key,
        target="IC 1805",
        filter_norm="Hα",
        collection=col,
        project=project,
        project_position=position,
    )


def finished(name, *projects):
    lib = Library.objects.get_or_create(
        name="completed", defaults={"mount_path": "/tmp/c", "role": LibraryRole.COMPLETED}
    )[0]
    fp = FinishedProject.objects.create(
        library=lib, rel_path=f"Astro/{name}", kind="astro", subject="IC 1805", name=name
    )
    fp.linked_projects.set(projects)
    return fp


@pytest.fixture
def heart():
    col = Collection.objects.create(name="Heart", objects_text="IC 1805", constellation="Cas")
    a = Project.objects.create(
        collection=col, season="2025", own_name="widefield", goals={"Hα": 20}, done_at=DONE, position=0
    )
    b = Project.objects.create(collection=col, season="2026", position=1)
    d1, d2 = ds(col, "a1", a, 0), ds(col, "a2", a, 1)
    d3, loose = ds(col, "b1", b, 0), ds(col, "loose")
    other = Collection.objects.create(name="Elsewhere")
    only = finished("2025 Heart", a)  # linked only here: the renderer would drop it
    shared = finished("Heart and Soul", a, Project.objects.create(collection=other, season="2026"))
    return {
        "col": col,
        "a": a,
        "b": b,
        "ds": [d1, d2, d3, loose],
        "other": other,
        "only": only,
        "shared": shared,
    }


def test_read_only_accounts_cant_create_change_or_delete_collections(viewer_client, heart):
    col = heart["col"]
    body = json.dumps({"name": "x", "dataset_ids": []})
    assert viewer_client.post("/api/v1/collections", body, content_type="application/json").status_code == 403
    r = viewer_client.patch(f"/api/v1/collections/{col.pk}", body, content_type="application/json")
    assert r.status_code == 403
    assert viewer_client.delete(f"/api/v1/collections/{col.pk}").status_code == 403
    assert viewer_client.get(f"/api/v1/collections/{col.pk}/impact").status_code == 200
    assert Collection.objects.filter(pk=col.pk, name="Heart").exists()


def test_refused_while_its_files_move(admin_client, heart, tmp_path):
    col = heart["col"]
    archive = Library.objects.create(name="big", mount_path=str(tmp_path / "big"), role="archive")
    active = Library.objects.create(name="fast", mount_path=str(tmp_path / "fast"), role="active")
    move = CollectionMove.objects.create(
        collection=col, direction="archive", from_library=active, to_library=archive, state="running"
    )
    imp = admin_client.get(f"/api/v1/collections/{col.pk}/impact").json()
    assert imp["move"] == "running" and imp["blockers"] == ["Its files are moving. Cancel the move first."]
    r = admin_client.delete(f"/api/v1/collections/{col.pk}")
    assert r.status_code == 409 and "Cancel the move first" in r.json()["message"]
    CollectionMove.objects.filter(pk=move.pk).update(state="queued")
    assert admin_client.get(f"/api/v1/collections/{col.pk}/impact").json()["move"] == "waiting"
    assert admin_client.delete(f"/api/v1/collections/{col.pk}").status_code == 409
    CollectionMove.objects.filter(pk=move.pk).update(state="done")
    assert admin_client.delete(f"/api/v1/collections/{col.pk}").status_code == 200


def test_refused_with_a_live_combined_master_and_allowed_once_its_deleted(admin_client, heart):
    col = heart["col"]
    cm = CombinedMaster.objects.create(
        collection=col, project=heart["a"], filter_norm="Hα", version=2, state="current"
    )
    imp = admin_client.get(f"/api/v1/collections/{col.pk}/impact").json()
    assert imp["combined"] == ["Hα v2"] and "Delete them first" in imp["blockers"][0]
    r = admin_client.delete(f"/api/v1/collections/{col.pk}")
    assert r.status_code == 409 and "Delete them first" in r.json()["message"]
    assert admin_client.delete(f"/api/v1/combined/{cm.pk}").status_code == 204
    assert admin_client.get(f"/api/v1/collections/{col.pk}/impact").json()["blockers"] == []
    assert admin_client.delete(f"/api/v1/collections/{col.pk}").status_code == 200


def test_delete_says_what_it_touches_and_undo_brings_back_the_same_ids(admin_client, heart):
    col, a, b = heart["col"], heart["a"], heart["b"]
    d1, d2, d3, loose = heart["ds"]
    imp = admin_client.get(f"/api/v1/collections/{col.pk}/impact").json()
    assert imp["datasets"] == 4
    assert imp["projects"] == [
        {"id": a.pk, "label": "2025 · widefield", "done": True, "goals_set": True},
        {"id": b.pk, "label": "2026", "done": False, "goals_set": False},
    ]
    assert imp["finished"] == ["2025 Heart", "Heart and Soul"] and imp["unoffered"] == ["2025 Heart"]
    assert imp["move"] is None and imp["combined"] == [] and imp["blockers"] == []

    r = admin_client.delete(f"/api/v1/collections/{col.pk}")
    assert r.status_code == 200, r.content
    out = r.json()
    assert out["warnings"] == ["2025 Heart: no longer offered to the renderer."]
    assert not Collection.objects.filter(pk=col.pk).exists()
    assert not Project.objects.filter(pk__in=[a.pk, b.pk]).exists()
    assert (
        Dataset.objects.filter(pk__in=[d.pk for d in heart["ds"]], collection=None, project=None).count() == 4
    )
    assert list(heart["only"].linked_projects.all()) == []
    change = Change.objects.get(pk=out["change_id"])
    assert change.kind == "collection" and change.summary == "Deleted collection Heart" and change.count == 4

    # meanwhile one dataset joins another collection: it stays there
    Dataset.objects.filter(pk=d3.pk).update(collection=heart["other"])
    r = admin_client.post(f"/api/v1/changes/{change.pk}/undo")
    assert r.status_code == 200, r.content
    assert r.json()["note"] == "Restored collection Heart."
    back = Collection.objects.get(pk=col.pk)
    assert back.name == "Heart"
    ra, rb = Project.objects.get(pk=a.pk), Project.objects.get(pk=b.pk)
    assert ra.collection_id == col.pk and ra.goals == {"Hα": 20} and ra.done_at == DONE
    assert ra.own_name == "widefield" and rb.season == "2026"
    assert [d.pk for d in ra.datasets.order_by("project_position")] == [d1.pk, d2.pk]
    assert list(rb.datasets.all()) == []
    assert Dataset.objects.get(pk=d3.pk).collection_id == heart["other"].pk
    assert Dataset.objects.get(pk=loose.pk).collection_id == col.pk
    assert list(heart["only"].linked_projects.all()) == [ra]
    assert ra in heart["shared"].linked_projects.all()

    second = admin_client.post(f"/api/v1/changes/{change.pk}/undo")
    assert second.status_code == 409
