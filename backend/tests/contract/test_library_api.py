"""Library and collections (spec 006, L23): suggestions say why, a dataset belongs to one collection, removing a
collection keeps its datasets, and the cards carry integration per filter and state."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Collection, Dataset, Rig

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 6, 21, 0, tzinfo=UTC)


def ds(key: str, target: str, filt: str, subs: int = 10, accepted_s: float = 3600) -> Dataset:
    return Dataset.objects.create(
        group_key=key,
        target=target,
        filter_norm=filt,
        display_name=f"{target} · {filt}",
        sub_count=subs,
        accepted_integration_s=accepted_s,
    )


def test_suggestion_by_name_and_one_collection_per_dataset(admin_client):
    ha, oiii = ds("a", "Heart Nebula", "Hα"), ds("b", "Heart Nebula", "OIII")
    r = admin_client.post(
        "/api/v1/collections",
        {"name": "Heart and Soul", "dataset_ids": [ha.pk]},
        content_type="application/json",
    )
    assert r.status_code == 201
    col = r.json()["id"]
    lib = admin_client.get("/api/v1/library").json()
    row = next(u for u in lib["ungrouped"] if u["dataset"]["id"] == oiii.pk)
    assert row["suggestion"]["collection_id"] == col and "Same object name" in row["suggestion"]["why"]
    other = Collection.objects.create(name="Elsewhere")
    admin_client.post(
        f"/api/v1/collections/{other.pk}/datasets", {"dataset_ids": [ha.pk]}, content_type="application/json"
    )
    ha.refresh_from_db()
    assert ha.collection_id == other.pk  # moved, not copied


def test_removing_a_collection_keeps_its_datasets_and_cards_add_up(admin_client):
    a, b = ds("c", "M 31", "L", accepted_s=7200), ds("d", "M 31", "Hα", accepted_s=3600)
    col = admin_client.post(
        "/api/v1/collections",
        {"name": "Andromeda", "dataset_ids": [a.pk, b.pk]},
        content_type="application/json",
    ).json()
    card = next(c for c in admin_client.get("/api/v1/library").json()["collections"] if c["id"] == col["id"])
    assert card["filters"] == {"L": 7200, "Hα": 3600} and card["accepted_integration_s"] == 10800
    r = admin_client.delete(f"/api/v1/collections/{col['id']}")
    assert r.status_code == 200 and r.json()["change_id"] and r.json()["warnings"] == []
    assert Dataset.objects.filter(pk__in=[a.pk, b.pk], collection=None).count() == 2


def test_candidates_list_same_name_datasets_from_elsewhere(admin_client):
    a, b = ds("e", "Soul Nebula", "Hα"), ds("f", "Soul Nebula", "OIII")
    col = Collection.objects.create(name="Soul")
    Dataset.objects.filter(pk=a.pk).update(collection=col)
    other = Collection.objects.create(name="Old Soul")
    Dataset.objects.filter(pk=b.pk).update(collection=other)
    rows = admin_client.get(f"/api/v1/collections/{col.pk}/candidates").json()
    assert [(r["dataset_id"], r["in_collection"]) for r in rows] == [(b.pk, "Old Soul")]
    assert "Same object name" in rows[0]["note"]


def test_framing_draws_solved_fields_over_the_reference(admin_client):
    """009 P10/P12: each solved dataset's field relative to the reference (most accepted integration)."""
    from apps.catalogue.models import Frame, FrameStatus, FrameType
    from apps.processing.models import PlateSolve

    col = Collection.objects.create(name="Cygnus")
    a, b = ds("p1", "NGC 7000", "Hα", accepted_s=36000), ds("p2", "NGC 7000", "OIII", accepted_s=3600)
    Dataset.objects.filter(pk__in=[a.pk, b.pk]).update(collection=col)
    for i, (d, ra) in enumerate(((a, 314.0), (b, 315.0))):
        f = Frame.objects.create(
            sha256=f"f{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            dataset=d,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
        )
        PlateSolve.objects.create(
            frame=f,
            state="solved",
            ra_deg=ra,
            dec_deg=44.0,
            rotation_deg=0,
            scale_arcsec=1.58,
            fov_w_deg=2.7,
            fov_h_deg=1.8,
        )
    rows = admin_client.get(f"/api/v1/collections/{col.pk}/framing").json()
    assert rows[0]["dataset_id"] == a.pk and rows[0]["reference"] and rows[0]["overlap"] == 1.0
    assert 40 < rows[1]["offset_arcmin"] < 45 and 0.5 < rows[1]["overlap"] < 0.8


def test_candidates_rank_by_solved_overlap_and_rotation(admin_client):
    """009 P11: with plate solves on both sides, candidates are ranked by coverage of the reference field and the
    note says centre offset, rotation and coverage."""
    from apps.catalogue.models import Frame, FrameStatus, FrameType
    from apps.processing.models import PlateSolve

    col = Collection.objects.create(name="Cygnus")
    a = ds("c1", "NGC 7000", "Hα", accepted_s=36000)
    Dataset.objects.filter(pk=a.pk).update(collection=col)
    near, far = ds("c2", "NGC 7000", "OIII"), ds("c3", "NGC 7000", "SII")
    for i, (d, ra, rot) in enumerate(((a, 314.0, 0), (near, 314.1, 182), (far, 315.0, 30))):
        f = Frame.objects.create(
            sha256=f"c{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            dataset=d,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
        )
        PlateSolve.objects.create(
            frame=f,
            state="solved",
            ra_deg=ra,
            dec_deg=44.0,
            rotation_deg=rot,
            scale_arcsec=1.58,
            fov_w_deg=2.7,
            fov_h_deg=1.8,
        )
    rows = admin_client.get(f"/api/v1/collections/{col.pk}/candidates").json()
    assert [r["dataset_id"] for r in rows][:2] == [near.pk, far.pk]
    assert rows[0]["rotation_diff"] == 2.0 and rows[0]["overlap"] > 0.9
    assert "Solved:" in rows[0]["note"] and "rotated 2°" in rows[0]["note"]


def test_library_stats_follow_the_filters(admin_client):
    """Owner 2026-10-10: frames, hours per filter and rig, kept and rejected rates, average SQM."""
    from datetime import date as d_

    from apps.catalogue.models import Frame, FrameStatus, FrameType, HeaderSnapshot, Night
    from apps.processing.models import MachineGrade

    a = ds("s1", "M 31", "Hα")
    for i, (day, verdict, sqm) in enumerate(((3, "accept", 20.5), (3, "reject", 19.5), (20, "accept", None))):
        n = Night.objects.get_or_create(site_key="s", date=d_(2026, 9, day))[0]
        f = Frame.objects.create(
            sha256=f"st{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            dataset=a,
            night=n,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
            exptime_s=1800,
        )
        MachineGrade.objects.create(frame=f, verdict=verdict, reason="")
        HeaderSnapshot.objects.create(frame=f, keywords={"SQM": {"value": sqm, "comment": ""}} if sqm else {})
    s = admin_client.get("/api/v1/library/stats").json()
    assert s["frames"] == 3 and s["hours"] == 1.5 and s["accepted_hours"] == 1.0
    assert (
        s["success_rate"] == 0.667
        and s["failure_rate"] == 0.333
        and s["avg_sqm"] == 20.0
        and s["nights"] == 2
    )
    assert list(s["by_filter"]) == ["Hα"]
    s = admin_client.get("/api/v1/library/stats?date_from=2026-09-10").json()
    assert s["frames"] == 1 and s["avg_sqm"] is None


def test_add_a_rig_and_set_its_mount(admin_client):
    """008 T18: a rig can be added before its first sub, and any rig given a mount type."""
    import json

    r = admin_client.post(
        "/api/v1/rigs",
        json.dumps(
            {
                "name": "Redcat 51 + 2600MC",
                "telescope": "Redcat 51",
                "camera": "ZWO ASI2600MC Pro",
                "focal_mm": 250,
                "mount": "equatorial",
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 201 and r.json()["mount"] == "equatorial"
    rid = r.json()["id"]
    assert Rig.objects.get(pk=rid).key == "Redcat 51|ZWO ASI2600MC Pro|250.0"
    again = admin_client.post(
        "/api/v1/rigs",
        json.dumps({"name": "x", "telescope": "Redcat 51", "camera": "ZWO ASI2600MC Pro", "focal_mm": 250}),
        content_type="application/json",
    )
    assert again.status_code == 409
    r = admin_client.patch(
        f"/api/v1/rigs/{rid}", json.dumps({"mount": "smart"}), content_type="application/json"
    )
    assert r.json()["mount"] == "smart"


def test_a_card_counts_every_sub_whether_calibrated_or_not(admin_client):
    """Captured time shows before calibration: split into usable, waiting and rejected (owner 2026-10-13)."""
    a = ds("e", "NGC 4038", "L", accepted_s=600)
    Dataset.objects.filter(pk=a.pk).update(integration_s=3000, rejected_integration_s=300)
    col = admin_client.post(
        "/api/v1/collections", {"name": "Antennae", "dataset_ids": [a.pk]}, content_type="application/json"
    ).json()
    card = next(c for c in admin_client.get("/api/v1/library").json()["collections"] if c["id"] == col["id"])
    assert card["filter_time"]["L"] == {"total_s": 3000, "accepted_s": 600, "rejected_s": 300}


def test_stats_read_sky_quality_from_either_header_form():
    """The SQM is read from the headers' keywords alone (2026-10-15: loading whole headers took over 3 s)."""
    from apps.catalogue.api_library import _sqm_by_frame
    from apps.catalogue.models import Frame, HeaderSnapshot

    a = Frame.objects.create(sha256="a" * 64, size_bytes=1, format="fits", first_seen_at=T)
    b = Frame.objects.create(sha256="b" * 64, size_bytes=1, format="fits", first_seen_at=T)
    HeaderSnapshot.objects.create(frame=a, keywords={"MPSAS": {"value": 21.3, "comment": ""}})
    HeaderSnapshot.objects.create(frame=b, keywords={"SQM": "20.1"})
    assert _sqm_by_frame([a.pk, b.pk], ("MPSAS", "SQM", "SKYQUAL")) == {a.pk: 21.3, b.pk: 20.1}


def test_each_rig_lists_the_filters_it_shot_through(admin_client):
    """So a filter choice can follow the chosen rig: a rig only offers filters its datasets used."""
    mono = Rig.objects.create(name="Askar + ATR", key="a", telescope="Askar 71F", camera="ATR2600M")
    osc = Rig.objects.create(name="Sony", key="b", telescope="TTArtisan", camera="Sony A73")
    for flt in ("Hα", "OIII", "Hα"):
        d = ds(f"m-{flt}-{Dataset.objects.count()}", "IC 1805", flt)
        d.rig = mono
        d.save()
    d = ds("o", "IC 1805", "OSC")
    d.rig = osc
    d.save()
    rigs = {r["name"]: r["filters"] for r in admin_client.get("/api/v1/rigs").json()}
    assert rigs == {"Askar + ATR": ["Hα", "OIII"], "Sony": ["OSC"]}
