"""006-DR-20/-24: projects inside a collection."""

import json

import pytest

from apps.catalogue.models import Collection, Dataset, Project

pytestmark = pytest.mark.django_db


def put(client, url, body):
    return client.put(url, json.dumps(body), content_type="application/json")


def test_projects_suggest_assign_and_order(admin_client):
    col = Collection.objects.create(name="NGC 7000")
    panels = [
        Dataset.objects.create(
            group_key=f"p{i}",
            display_name=f"p{i}",
            target="NGC 7000",
            filter_norm="Hα",
            panel=i,
            collection=col,
        )
        for i in (1, 2, 4)
    ]
    single = Dataset.objects.create(
        group_key="s", display_name="s", target="NGC 7000", filter_norm="Hα", collection=col
    )
    made = admin_client.post(f"/api/v1/collections/{col.pk}/projects/suggest").json()
    mosaic = next(p for p in made if p["kind"] == "mosaic")
    assert (
        mosaic["name"].startswith("4-panel mosaic")
        and mosaic["panels"] == [1, 2, 4]
        and mosaic["missing_panels"] == [3]
    )
    assert mosaic["dataset_ids"] == [d.pk for d in panels]
    other = next(p for p in made if p["kind"] == "single")
    assert other["dataset_ids"] == [single.pk]
    r = admin_client.patch(
        f"/api/v1/projects/{mosaic['id']}",
        json.dumps({"name": "6-panel mosaic 2026", "planned_panels": 6}),
        content_type="application/json",
    ).json()
    assert r["missing_panels"] == [3, 5, 6]
    # move the single field into the mosaic, in a chosen order; then reorder projects
    r = put(
        admin_client,
        f"/api/v1/projects/{mosaic['id']}/datasets",
        {"ids": [panels[2].pk, single.pk, panels[0].pk]},
    ).json()
    assert r["dataset_ids"] == [panels[2].pk, single.pk, panels[0].pk]
    listed = admin_client.get(f"/api/v1/collections/{col.pk}/projects").json()
    assert panels[1].pk in listed["unassigned"]
    order = put(
        admin_client, f"/api/v1/collections/{col.pk}/projects/order", {"ids": [other["id"], mosaic["id"]]}
    ).json()
    assert [p["id"] for p in order] == [other["id"], mosaic["id"]]
    assert (
        put(admin_client, f"/api/v1/collections/{col.pk}/projects/order", {"ids": [mosaic["id"]]}).status_code
        == 422
    )
    assert admin_client.delete(f"/api/v1/projects/{other['id']}").status_code == 204
    assert not Project.objects.filter(pk=other["id"]).exists()


def test_a_project_only_takes_its_collections_datasets(admin_client):
    col, elsewhere = Collection.objects.create(name="A"), Collection.objects.create(name="B")
    d = Dataset.objects.create(group_key="x", display_name="x", target="M 31", collection=elsewhere)
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/projects",
        json.dumps({"name": "P", "dataset_ids": [d.pk]}),
        content_type="application/json",
    )
    assert r.status_code == 422
