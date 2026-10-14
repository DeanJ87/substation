"""Merging target names in a collection (spec 006): datasets that differ only by the name written at capture
time regroup into one, every filter follows, and nothing on disk changes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Collection, Dataset, Frame, FrameStatus, FrameType
from apps.catalogue.services.grouping import assign_dataset, refresh_dataset
from apps.processing.models import Master

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 6, 21, 0, tzinfo=UTC)


def light(i: int, obj: str, filt: str) -> Frame:
    f = Frame.objects.create(
        sha256=f"{i}".rjust(64, "a"),
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        object=obj,
        target=obj,
        filter_norm=filt,
        filter_raw=filt,
        camera="ATR2600M",
        telescope="Askar 71F",
        xbin=1,
        ybin=1,
        gain=120,
        offset=80,
        exptime_s=300,
        date_obs_utc=T,
    )
    assign_dataset(f)
    f.save()
    refresh_dataset(f.dataset)
    return f


def test_merge_names_regroups_every_filter(admin_client, monkeypatch):
    import apps.ingest.resolve as resolve

    real = resolve.resolve_frame

    def keep_values(frame, has_integration=None):  # no header snapshots in this test: re-apply the alias only
        from apps.processing.config import processing_settings

        frame.target = processing_settings()["equipment"].get("target", {}).get(frame.object, frame.object)
        old, new = assign_dataset(frame)
        frame.save()
        return old, new

    monkeypatch.setattr("apps.ingest.tasks.reresolve.resolve_frame", keep_values)
    col = Collection.objects.create(name="Soul Nebula")
    for i, (obj, filt) in enumerate(
        [
            ("Soul Nebula", "Hα"),
            ("Soul Nebula", "Hα"),
            ("TestSoulNebula", "Hα"),
            ("IC 1848 - Soul Nebula", "Hα"),
            ("TestSoulNebula", "OIII"),
            ("Soul Nebula", "OIII"),
        ]
    ):
        light(i, obj, filt)
    Dataset.objects.update(collection=col)
    keep = Dataset.objects.get(target="Soul Nebula", filter_norm="Hα")
    Master.objects.create(dataset=keep, version=1, state="current")
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/merge-names",
        {"names": ["TestSoulNebula", "IC 1848 - Soul Nebula"], "into": "Soul Nebula"},
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    from apps.ingest.tasks.reresolve import reresolve_targets

    reresolve_targets.call(["TestSoulNebula", "IC 1848 - Soul Nebula"])  # what the queued job does
    left = {(d.target, d.filter_norm): d.sub_count for d in Dataset.objects.all()}
    assert left == {("Soul Nebula", "Hα"): 4, ("Soul Nebula", "OIII"): 2}
    assert Master.objects.get(dataset=keep).state == "stale"  # it gained subs
    bad = admin_client.post(
        f"/api/v1/collections/{col.pk}/merge-names",
        {"names": ["M 31"], "into": "Soul Nebula"},
        content_type="application/json",
    )
    assert bad.status_code == 422
    assert real is resolve.resolve_frame


def test_a_merged_away_datasets_stack_moves_with_its_subs(admin_client, monkeypatch):
    """A dataset emptied by a merge hands its stacks to the dataset now holding their subs, marked stale."""
    from apps.ingest.tasks.reresolve import reresolve_targets
    from apps.processing.models import MasterMember

    def keep_values(frame, has_integration=None):
        from apps.processing.config import processing_settings

        frame.target = processing_settings()["equipment"].get("target", {}).get(frame.object, frame.object)
        old, new = assign_dataset(frame)
        frame.save()
        return old, new

    monkeypatch.setattr("apps.ingest.tasks.reresolve.resolve_frame", keep_values)
    col = Collection.objects.create(name="Soul")
    a, b = light(10, "Soul Nebula", "Hα"), light(11, "IC 1848", "Hα")
    Dataset.objects.update(collection=col)
    gone = b.dataset
    assert gone is not None
    m = Master.objects.create(dataset=gone, version=1, state="current")
    MasterMember.objects.create(master=m, frame=b, included=True)
    admin_client.post(
        f"/api/v1/collections/{col.pk}/merge-names",
        {"names": ["IC 1848"], "into": "Soul Nebula"},
        content_type="application/json",
    )
    reresolve_targets.call(["IC 1848"])
    m.refresh_from_db()
    assert m.dataset_id == a.dataset_id and m.state == "stale" and "IC 1848" in m.state_reason
    assert not Dataset.objects.filter(pk=gone.pk).exists()


def test_a_dataset_made_by_a_merge_stays_in_the_collection(admin_client, monkeypatch):
    """006, 2026-10-14: merging M 42 and orion moved every regrouped dataset out of the collection."""
    from apps.ingest.tasks.reresolve import reresolve_targets

    def keep_values(frame, has_integration=None):
        from apps.processing.config import processing_settings

        frame.target = processing_settings()["equipment"].get("target", {}).get(frame.object, frame.object)
        old, new = assign_dataset(frame)
        frame.save()
        return old, new

    monkeypatch.setattr("apps.ingest.tasks.reresolve.resolve_frame", keep_values)
    col = Collection.objects.create(name="M 42 - Orion Nebula")
    light(20, "M 42", "Hα")
    light(21, "orion", "B")  # only under the other name: the merge makes a new M 42 · B
    Dataset.objects.update(collection=col)
    admin_client.post(
        f"/api/v1/collections/{col.pk}/merge-names",
        {"names": ["orion"], "into": "M 42"},
        content_type="application/json",
    )
    reresolve_targets.call(["orion"])
    made = Dataset.objects.get(target="M 42", filter_norm="B")
    assert made.collection_id == col.pk
    assert set(Dataset.objects.values_list("collection_id", flat=True)) == {col.pk}
