"""The master viewer's side panel (004-DR-36, 010-DR-30): a master's integration and subs, and for a stitched or
stacked master or a palette, each panel, master or filter it holds."""

from __future__ import annotations

import pytest

from apps.catalogue.models import Collection, Dataset
from apps.processing.api_masters import palette_integration
from apps.processing.models import CombinedMaster, Master, MasterState

pytestmark = pytest.mark.django_db


def ds(col: Collection, key: str, filt: str, panel: int | None = None) -> Dataset:
    return Dataset.objects.create(
        group_key=key, target="NGC 7000", filter_norm=filt, display_name=key, collection=col, panel=panel
    )


def test_a_masters_view_carries_its_integration(admin_client):
    col = Collection.objects.create(name="NGC 7000")
    m = Master.objects.create(
        dataset=ds(col, "a", "Hα"),
        version=2,
        state=MasterState.CURRENT,
        output_path="/nowhere/master_v2.fit",
        integration_s=64200,
        sub_count=214,
        session_count=9,
    )
    look = admin_client.get(f"/api/v1/stacks/{m.pk}/view").json()
    assert look["integration"] == {
        "kind": "master",
        "filter": "Hα",
        "integration_s": 64200,
        "subs": 214,
        "sessions": 9,
        "parts": [],
    }


def test_a_mosaic_lists_its_panels_and_counts_only_the_ones_used(admin_client):
    col = Collection.objects.create(name="NGC 7000")
    a, b, c = ds(col, "p1", "Hα", 1), ds(col, "p2", "Hα", 2), ds(col, "p3", "Hα", 3)
    cm = CombinedMaster.objects.create(
        collection=col,
        filter_norm="Hα",
        version=1,
        method="stitch",
        state=MasterState.CURRENT,
        output_path="/nowhere/mosaic.fit",
        inputs=[
            {
                "master": 1,
                "dataset": b.pk,
                "label": "Askar · Hα · Panel 2",
                "integration_s": 3600,
                "subs": 12,
            },
            {
                "master": 2,
                "dataset": a.pk,
                "label": "Askar · Hα · Panel 1",
                "integration_s": 7200,
                "subs": 24,
            },
            {
                "master": 3,
                "dataset": c.pk,
                "label": "Askar · Hα · Panel 3",
                "integration_s": 1800,
                "subs": 6,
                "registered": False,
            },
        ],
        integration_s=12600,
    )
    i = admin_client.get(f"/api/v1/combined/{cm.pk}/view").json()["integration"]
    assert i["kind"] == "stitch" and i["integration_s"] == 10800 and i["subs"] == 36
    assert [(p["panel"], p["used"]) for p in i["parts"]] == [(1, True), (2, True), (3, False)]


def test_a_palette_breaks_down_by_filter():
    col = Collection.objects.create(name="NGC 7000")
    for filt, secs, subs in (("Hα", 36000, 120), ("OIII", 28800, 96)):
        d = ds(col, filt, filt)
        CombinedMaster.objects.create(
            collection=col,
            filter_norm=filt,
            version=1,
            method="stack",
            state=MasterState.CURRENT,
            inputs=[{"master": 1, "dataset": d.pk, "label": filt, "integration_s": secs, "subs": subs}],
            integration_s=secs,
        )
    i = palette_integration(col.pk, None, "hoo")
    assert i is not None and i.integration_s == 64800 and i.subs == 216
    assert [(p.filter, p.integration_s) for p in i.parts] == [("Hα", 36000), ("OIII", 28800)]
    assert palette_integration(col.pk, None, "sho") is None  # no SII yet
