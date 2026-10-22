"""006-DR-20/-24 and the 2026-10-22 amendment: projects inside a collection, one per season."""

import json
from datetime import date
from itertools import count

import pytest

from apps.catalogue.models import Change, Collection, Dataset, DatasetNight, Night, Project, Rig
from apps.catalogue.services import projects as svc
from apps.finished.models import FinishedProject
from apps.libraries.models import Library, LibraryRole
from apps.processing.models import CombinedMaster

pytestmark = pytest.mark.django_db
_n = count()


def put(client, url, body):
    return client.put(url, json.dumps(body), content_type="application/json")


def post(client, url, body=None):
    return client.post(url, json.dumps(body or {}), content_type="application/json")


def patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type="application/json")


def ds(col, nights, rig=None, panel=None, filt="Hα", hours=1.0):
    k = next(_n)
    d = Dataset.objects.create(
        group_key=f"d{k}",
        display_name=f"d{k}",
        target="IC 1805",
        filter_norm=filt,
        panel=panel,
        rig=rig,
        collection=col,
        accepted_integration_s=hours * 3600 * len(nights),
    )
    for n in nights:
        night, _ = Night.objects.get_or_create(site_key="50,-4", date=n)
        DatasetNight.objects.create(dataset=d, night=night, integration_s=hours * 3600)
    return d


def rig(name):
    return Rig.objects.create(key=name, name=name)


def finished(name, *projects):
    lib = Library.objects.get_or_create(
        name="completed", defaults={"mount_path": "/tmp/c", "role": LibraryRole.COMPLETED}
    )[0]
    fp = FinishedProject.objects.create(
        library=lib, rel_path=f"Astro/{name}", kind="astro", subject="IC 1805", name=name
    )
    fp.linked_projects.set(projects)
    return fp


def undo(client, change_id):
    r = client.post(f"/api/v1/changes/{change_id}/undo")
    assert r.status_code == 200, r.content
    return r.json()


def test_seasons_runs_and_labels():
    assert svc.season_label(date(2026, 9, 1), date(2026, 11, 1)) == "2026"
    assert svc.season_label(date(2025, 11, 20), date(2026, 1, 10)) == "2025–26"
    runs = svc.season_runs([date(2025, 11, 20), date(2026, 1, 10), date(2026, 9, 1), date(2026, 9, 3)])
    assert runs == [(date(2025, 11, 20), date(2026, 1, 10)), (date(2026, 9, 1), date(2026, 9, 3))]


def test_sort_into_seasons_never_splits_by_rig_or_panel(admin_client):
    """The IC 1805 shape: a 2-panel mosaic and single fields on three rigs, over two seasons."""
    col = Collection.objects.create(name="IC 1805")
    askar, sony, tt = rig("Askar 71F + ATR2600M"), rig("Askar 71F + Sony A73"), rig("TTArtisan + Sony A73")
    winter = [
        ds(col, [date(2025, 11, 20), date(2025, 12, 2)], rig=sony),
        ds(col, [date(2026, 1, 10)], rig=tt),
    ]
    autumn = [
        ds(col, [date(2026, 9, 1)], rig=askar, panel=1),
        ds(col, [date(2026, 9, 2)], rig=askar, panel=2),
        ds(col, [date(2026, 9, 20)], rig=askar),
        ds(col, [date(2026, 10, 5)], rig=tt),
    ]
    r = post(admin_client, f"/api/v1/collections/{col.pk}/projects/suggest").json()
    assert r["placed"] == 6 and r["joined"] == [] and r["change_id"]
    made = {p["season"]: p for p in r["created"]}
    assert set(made) == {"2025–26", "2026"}
    assert sorted(made["2025–26"]["dataset_ids"]) == sorted(d.pk for d in winter)
    assert sorted(made["2026"]["dataset_ids"]) == sorted(d.pk for d in autumn)
    assert made["2026"]["label"] == made["2026"]["name"] == "2026" and made["2026"]["own_name"] == ""
    assert made["2026"]["kind"] == "mosaic" and made["2026"]["kind_auto"] == "mosaic"
    assert made["2026"]["kind_override"] is None
    assert made["2025–26"]["kind"] == "single"
    # a dataset shot later the same season joins that season's project
    late = ds(col, [date(2026, 10, 30)], rig=sony)
    r = post(admin_client, f"/api/v1/collections/{col.pk}/projects/suggest").json()
    assert r["created"] == [] and [p["id"] for p in r["joined"]] == [made["2026"]["id"]]
    assert late.pk in r["joined"][0]["dataset_ids"]
    # undo takes it out again
    undo(admin_client, r["change_id"])
    assert Dataset.objects.get(pk=late.pk).project_id is None


def test_create_assign_order_and_undo(admin_client):
    col = Collection.objects.create(name="NGC 7000")
    a, b = ds(col, [date(2026, 8, 1)]), ds(col, [date(2026, 8, 2)])
    r = post(admin_client, f"/api/v1/collections/{col.pk}/projects", {"name": "widefield", "season": "2026"})
    assert r.status_code == 201
    p = r.json()
    assert p["label"] == "2026 · widefield" and p["own_name"] == "widefield" and p["change_id"]
    default = post(admin_client, f"/api/v1/collections/{col.pk}/projects", {}).json()
    assert default["season"] == str(date.today().year)
    r = put(admin_client, f"/api/v1/projects/{p['id']}/datasets", {"ids": [b.pk, a.pk]}).json()
    assert r["dataset_ids"] == [b.pk, a.pk]
    undo(admin_client, r["change_id"])
    assert Dataset.objects.filter(project_id=p["id"]).count() == 0
    order = put(
        admin_client, f"/api/v1/collections/{col.pk}/projects/order", {"ids": [default["id"], p["id"]]}
    ).json()
    assert [x["id"] for x in order] == [default["id"], p["id"]]
    assert (
        put(admin_client, f"/api/v1/collections/{col.pk}/projects/order", {"ids": [p["id"]]}).status_code
        == 422
    )


def test_a_project_only_takes_its_collections_datasets(admin_client):
    col, elsewhere = Collection.objects.create(name="A"), Collection.objects.create(name="B")
    d = Dataset.objects.create(group_key="x", display_name="x", target="M 31", collection=elsewhere)
    r = post(admin_client, f"/api/v1/collections/{col.pk}/projects", {"name": "P", "dataset_ids": [d.pk]})
    assert r.status_code == 422


def test_effective_kind_and_override(admin_client):
    col = Collection.objects.create(name="M 31")
    p = Project.objects.create(collection=col, season="2026")
    d = ds(col, [date(2026, 9, 1)], panel=1)
    Dataset.objects.filter(pk=d.pk).update(project=p)
    url = f"/api/v1/projects/{p.pk}"
    assert (
        admin_client.get(f"/api/v1/collections/{col.pk}/projects").json()["projects"][0]["kind"] == "single"
    )
    r = patch(admin_client, url, {"planned_panels": 4}).json()
    assert r["kind"] == "mosaic" and r["kind_auto"] == "mosaic" and r["missing_panels"] == [2, 3, 4]
    r = patch(admin_client, url, {"kind": "single"}).json()
    assert r["kind"] == "single" and r["kind_auto"] == "mosaic" and r["kind_override"] == "single"
    p.refresh_from_db()
    assert p.kind == "single" and svc.effective_kind(p) == "single"
    r = patch(admin_client, url, {"kind": "auto"}).json()
    assert r["kind"] == "mosaic" and r["kind_override"] is None
    undo(admin_client, r["change_id"])
    p.refresh_from_db()
    assert p.kind_override == "single"


def test_done_projects_drop_out_of_the_goals(admin_client):
    col = Collection.objects.create(name="M 81")
    old = Project.objects.create(collection=col, season="2025", goals={"Hα": 5})
    Project.objects.create(collection=col, season="2026", goals={"Hα": 10})
    assert admin_client.get(f"/api/v1/collections/{col.pk}").json()["card"]["goals"] == {"Hα": 15}
    r = patch(admin_client, f"/api/v1/projects/{old.pk}", {"done": True}).json()
    assert r["done"] and r["done_at"]
    assert admin_client.get(f"/api/v1/collections/{col.pk}").json()["card"]["goals"] == {"Hα": 10}
    undo(admin_client, r["change_id"])
    assert Project.objects.get(pk=old.pk).done_at is None


def test_merge_moves_datasets_unions_goals_and_undoes(admin_client):
    col = Collection.objects.create(name="IC 1805")
    into = Project.objects.create(
        collection=col, season="2026", goals={"Hα": 10}, kind_override="mosaic", planned_panels=2
    )
    other = Project.objects.create(
        collection=col, season="2026", goals={"Hα": 20, "OIII": 5}, kind_override="single"
    )
    keep = ds(col, [date(2026, 9, 1)], panel=1)
    moved = [ds(col, [date(2026, 9, 3)]), ds(col, [date(2026, 9, 4)], filt="OIII")]
    Dataset.objects.filter(pk=keep.pk).update(project=into, project_position=0)
    for i, d in enumerate(moved):
        Dataset.objects.filter(pk=d.pk).update(project=other, project_position=i)
    cm = CombinedMaster.objects.create(collection=col, project=other, filter_norm="Hα", version=1)
    fp = finished("2026 Heart", into)
    imp = admin_client.get(f"/api/v1/projects/{other.pk}/impact", {"into": into.pk}).json()
    assert imp["combined"] == ["Hα v1"] and imp["finished"] == [] and imp["goal_conflicts"]
    r = post(
        admin_client, f"/api/v1/collections/{col.pk}/projects/merge", {"into": into.pk, "from": [other.pk]}
    )
    assert r.status_code == 200, r.content
    out = r.json()
    assert out["project"]["dataset_ids"] == [keep.pk, *(d.pk for d in moved)]
    assert out["project"]["goals"] == {"Hα": 20, "OIII": 5}
    assert out["project"]["kind_override"] == "mosaic" and out["project"]["planned_panels"] == 2
    assert any("Hα" in w for w in out["warnings"])
    assert not Project.objects.filter(pk=other.pk).exists()
    assert CombinedMaster.objects.get(pk=cm.pk).project_id == into.pk
    assert list(fp.linked_projects.all()) == [into]
    assert Change.objects.get(pk=out["change_id"]).kind == "project"
    undo(admin_client, out["change_id"])
    back = Project.objects.get(pk=other.pk)  # the same pk
    assert back.goals == {"Hα": 20, "OIII": 5} and back.kind_override == "single"
    assert sorted(back.datasets.values_list("pk", flat=True)) == sorted(d.pk for d in moved)
    assert CombinedMaster.objects.get(pk=cm.pk).project_id == other.pk
    into.refresh_from_db()
    assert into.goals == {"Hα": 10} and list(into.datasets.all()) == [keep]


def test_merge_is_refused_when_an_absorbed_project_is_linked_to_a_finished_image(admin_client):
    col = Collection.objects.create(name="IC 1805")
    into = Project.objects.create(collection=col, season="2026")
    other = Project.objects.create(collection=col, season="2026")
    finished("2026 Heart SHO", other)
    r = post(
        admin_client, f"/api/v1/collections/{col.pk}/projects/merge", {"into": into.pk, "from": [other.pk]}
    )
    assert r.status_code == 409 and "2026 Heart SHO" in r.json()["message"]
    assert Project.objects.filter(pk=other.pk).exists()


def test_merge_service_can_repoint_finished_links(admin_user):
    col = Collection.objects.create(name="IC 1805")
    into = Project.objects.create(collection=col, season="2026")
    other = Project.objects.create(collection=col, season="2026")
    fp = finished("2026 Heart SHO", other)
    change, _ = svc.merge(into.pk, [other.pk], admin_user, allow_linked=True)
    assert list(fp.linked_projects.all()) == [into]
    svc.undo(change.data)
    assert list(fp.linked_projects.all()) == [Project.objects.get(pk=other.pk)]


def test_split_by_rig_and_by_panel_and_undo(admin_client):
    col = Collection.objects.create(name="IC 1805")
    a, b = rig("Askar"), rig("TTArtisan")
    p = Project.objects.create(collection=col, season="2026", goals={"Hα": 10})
    big = ds(col, [date(2026, 9, 1), date(2026, 9, 2)], rig=a, panel=1)
    small = ds(col, [date(2026, 9, 3)], rig=b, panel=2)
    Dataset.objects.filter(pk__in=[big.pk, small.pk]).update(project=p)
    r = post(admin_client, f"/api/v1/projects/{p.pk}/split", {"by": "rig"}).json()
    assert r["project"]["dataset_ids"] == [big.pk]
    assert [(c["label"], c["dataset_ids"]) for c in r["created"]] == [("2026 · TTArtisan", [small.pk])]
    assert any("Goals stay" in w for w in r["warnings"])
    undo(admin_client, r["change_id"])
    assert sorted(p.datasets.values_list("pk", flat=True)) == sorted([big.pk, small.pk])
    assert col.projects.count() == 1
    r = post(admin_client, f"/api/v1/projects/{p.pk}/split", {"by": "panel"}).json()
    assert [c["label"] for c in r["created"]] == ["2026 · Panel 2"]
    one = post(admin_client, f"/api/v1/projects/{p.pk}/split", {"by": "panel"})
    assert one.status_code == 409
    r = post(
        admin_client,
        f"/api/v1/projects/{r['created'][0]['id']}/split",
        {"by": "datasets", "dataset_ids": [small.pk]},
    )
    assert r.status_code == 409  # can't empty a project


def test_delete_is_refused_with_combined_masters_else_keeps_datasets_and_undoes(admin_client):
    col = Collection.objects.create(name="IC 1805")
    p = Project.objects.create(collection=col, season="2026", own_name="widefield")
    d = ds(col, [date(2026, 9, 1)])
    Dataset.objects.filter(pk=d.pk).update(project=p, project_position=0)
    cm = CombinedMaster.objects.create(collection=col, project=p, filter_norm="Hα", version=1)
    r = admin_client.delete(f"/api/v1/projects/{p.pk}")
    assert r.status_code == 409 and "Hα v1" in r.json()["message"]
    cm.delete()
    fp = finished("2026 Heart", p)
    r = admin_client.delete(f"/api/v1/projects/{p.pk}")
    assert r.status_code == 200
    out = r.json()
    assert any("2026 Heart" in w for w in out["warnings"])
    assert not Project.objects.filter(pk=p.pk).exists()
    assert (
        Dataset.objects.get(pk=d.pk).collection_id == col.pk
        and Dataset.objects.get(pk=d.pk).project_id is None
    )
    undo(admin_client, out["change_id"])
    back = Project.objects.get(pk=p.pk)
    assert back.own_name == "widefield" and list(back.datasets.all()) == [d]
    assert list(fp.linked_projects.all()) == [back]


def test_held_groups_are_listed_for_review(admin_client):
    col = Collection.objects.create(name="IC 1805")
    a = Project.objects.create(
        collection=col, season="2026", needs_review=True, review_reason="Named by hand: A, B"
    )
    b = Project.objects.create(
        collection=col, season="2026", needs_review=True, review_reason="Named by hand: A, B"
    )
    ds_a = ds(col, [date(2026, 9, 1)], hours=3)
    Dataset.objects.filter(pk=ds_a.pk).update(project=a)
    review = admin_client.get(f"/api/v1/collections/{col.pk}/projects").json()["review"]
    assert review == [
        {
            "season": "2026",
            "project_ids": [a.pk, b.pk],
            "into": a.pk,
            "reasons": ["Named by hand: A, B"],
            "mergeable": True,
        }
    ]
    patch(admin_client, f"/api/v1/projects/{b.pk}", {"needs_review": False})
    assert admin_client.get(f"/api/v1/collections/{col.pk}/projects").json()["review"] == []
