"""Spec 018: one scope, the same meaning on every list."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Collection, Dataset, DatasetNight, Frame, FrameStatus, FrameType, Night, Rig
from apps.catalogue.scope import Scope, apply
from apps.processing.models import CalibrationMatch, MachineGrade, MatchState

pytestmark = pytest.mark.django_db
T = datetime(2026, 10, 11, 22, tzinfo=UTC)


@pytest.fixture
def world():
    askar = Rig.objects.create(key="askar|atr", name="Askar 71F + ATR2600M", camera="ATR2600M")
    sony = Rig.objects.create(key="sam|a7", name="Samyang 135 + A7 III", camera="ILCE-7M3")
    m81 = Collection.objects.create(name="M 81 - Bode's Galaxy")
    home = Night.objects.create(
        site_key="54.99,-1.66", date=date(2026, 10, 11), site_lat=54.99, site_lon=-1.66
    )
    away = Night.objects.create(site_key="-33.9,151.2", date=date(2026, 2, 3), site_lat=-33.9, site_lon=151.2)
    out = {}
    for i, (rig, filt, night, coll) in enumerate(
        [(askar, "L", home, m81), (askar, "Ha", away, m81), (sony, "OSC", home, None)]
    ):
        d = Dataset.objects.create(
            group_key=f"g{i}",
            target="M 81" if coll else "Milky Way",
            filter_norm=filt,
            display_name=f"d{i}",
            rig=rig,
            collection=coll,
            camera=rig.camera,
        )
        DatasetNight.objects.create(dataset=d, night=night)
        f = Frame.objects.create(
            sha256=f"{i:064x}",
            size_bytes=1,
            format="fits",
            first_seen_at=T,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
            dataset=d,
            night=night,
            filter_norm=filt,
            camera=rig.camera,
            target=d.target,
            site_lat=night.site_lat,
            site_lon=night.site_lon,
            exptime_s=60,
            gain=100,
            offset=30,
        )
        MachineGrade.objects.create(frame=f, verdict="reject", reason="cloud")
        CalibrationMatch.objects.create(
            frame=f, state=MatchState.AWAITING, reason="Awaiting calibration: no 60 s dark."
        )
        out[i] = (d, f)
    return {"askar": askar, "sony": sony, "m81": m81, "home": home, "away": away, "ds": out}


@pytest.mark.parametrize(
    ("scope", "frames", "datasets", "nights"),
    [
        ({}, {0, 1, 2}, {0, 1, 2}, 2),
        ({"rig": "askar"}, {0, 1}, {0, 1}, 2),
        ({"filter": "ha"}, {1}, {1}, 1),  # names match whatever the case
        ({"site": "54.99,-1.66"}, {0, 2}, {0, 2}, 1),
        ({"lat": 55.0, "lon": -1.7, "within_km": 10}, {0, 2}, None, 1),
        ({"date": date(2026, 2, 3)}, {1}, {1}, 1),
        ({"date_from": date(2026, 3, 1)}, {0, 2}, {0, 2}, 1),
        ({"collection": "m81", "camera": "ATR2600M"}, {0, 1}, {0, 1}, 2),
        ({"q": "october"}, {0, 2}, {0, 2}, 1),  # a month, as search reads it
        ({"q": "bode"}, {0, 1}, {0, 1}, None),  # a name
    ],
)
def test_each_input_means_the_same_on_every_kind(world, scope, frames, datasets, nights):
    ids = {"askar": world["askar"].pk, "m81": world["m81"].pk}
    s = Scope(
        **{
            k: ids.get(v, v) if isinstance(v, str) and k in ("rig", "collection") else v
            for k, v in scope.items()
        }
    )
    by_frame = {f.pk: i for i, (_, f) in world["ds"].items()}
    by_ds = {d.pk: i for i, (d, _) in world["ds"].items()}
    assert {by_frame[f.pk] for f in apply(Frame.objects.all(), s, "frame")} == frames
    assert {by_frame[m.frame_id] for m in apply(CalibrationMatch.objects.all(), s, "match")} == frames
    if datasets is not None:
        assert {by_ds[d.pk] for d in apply(Dataset.objects.all(), s, "dataset")} == datasets
    if nights is not None:
        assert apply(Night.objects.all(), s, "night").count() == nights


def test_endpoints_take_the_scope(world, admin_client):
    rig = world["askar"].pk
    shop = admin_client.get(f"/api/v1/calibration/shopping?rig={rig}").json()
    assert sum(n["subs"] for n in shop["needs"]) == 2
    assert len(admin_client.get(f"/api/v1/calibration/blocking?rig={rig}").json()) == 2
    review = admin_client.get("/api/v1/review?filter=OSC").json()
    assert [len(g["subs"]) for g in review] == [1]
    places = admin_client.get("/api/v1/map?since=2026-10-01").json()  # the older name still works
    assert {round(p["lat"]) for p in places["places"]} == {55}


# ---- SC2/SC3 (2026-10-15): the Library and the older list endpoints take the same scope -------------------------


def test_library_lists_and_counts_only_what_the_scope_covers(world, admin_client):
    Dataset.objects.update(sub_count=1)
    whole = admin_client.get("/api/v1/library").json()
    assert whole["counts"]["datasets"] == 3 and len(whole["ungrouped"]) == 1
    # Ha on the Askar: only M 81, and its card counts only that dataset and its one night
    lib = admin_client.get(f"/api/v1/library?rig={world['askar'].pk}&filter=Ha").json()
    assert lib["counts"] == {"datasets": 1, "collections": 1, "ungrouped": 0}
    card = lib["collections"][0]
    assert card["datasets"] == 1 and list(card["filters"]) == ["Ha"] and card["nights"] == ["2026-02-03"]
    # a range of nights narrows the card's sessions too, not only which collections show
    lib = admin_client.get("/api/v1/library?date_from=2026-10-01").json()
    assert lib["collections"][0]["nights"] == ["2026-10-11"] and len(lib["ungrouped"]) == 1
    assert admin_client.get("/api/v1/library?q=milky").json()["counts"]["collections"] == 0


def test_library_stats_take_the_scope_and_a_rig_by_name(world, admin_client):
    by_id = admin_client.get(f"/api/v1/library/stats?rig={world['askar'].pk}").json()
    by_name = admin_client.get("/api/v1/library/stats?rig=Askar 71F %2B ATR2600M").json()
    assert by_id["frames"] == by_name["frames"] == 2
    assert admin_client.get("/api/v1/library/stats?rig=no such rig").json()["frames"] == 0
    s = admin_client.get("/api/v1/library/stats?filter=OSC&date_from=2026-10-01").json()
    assert s["frames"] == 1 and list(s["by_filter"]) == ["OSC"]
    # a binned sub still counts, through the dataset it was in (spec 011)
    d, f = world["ds"][1]
    Frame.objects.filter(pk=f.pk).update(status=FrameStatus.BINNED, dataset=None, binned_dataset=d)
    s = admin_client.get(f"/api/v1/library/stats?collection={world['m81'].pk}").json()
    assert s["frames"] == 2 and s["binned"] == 1


def test_frames_and_datasets_take_the_scope_and_their_older_names(world, admin_client):
    def frames(qs: str) -> int:
        return len(admin_client.get(f"/api/v1/frames?{qs}").json()["items"])

    assert frames(f"rig={world['askar'].pk}") == 2
    assert frames("date=2026-02-03") == frames("night=2026-02-03") == 1  # `night`: the older name
    assert frames("q=october") == 2 and frames("q=bode") == 2
    Frame.objects.filter(pk=world["ds"][2][1].pk).update(object="Cygnus wide")
    assert frames("q=cygnus") == 1  # free text still finds the OBJECT header
    first = admin_client.get("/api/v1/frames?limit=2").json()
    rest = admin_client.get(f"/api/v1/frames?limit=2&cursor={first['next_cursor']}").json()
    assert len(first["items"]) == 2 and len(rest["items"]) == 1 and rest["next_cursor"] is None

    def datasets(qs: str) -> set[str]:
        return {d["target"] for d in admin_client.get(f"/api/v1/datasets?{qs}").json()["items"]}

    Dataset.objects.update(sub_count=1)
    assert datasets("target=M 8") == {"M 81"}  # `target` here is still part of the name
    assert datasets("site=-33.9,151.2") == {"M 81"}
    assert datasets(f"collection={world['m81'].pk}&filter=l") == {"M 81"}
    assert datasets("camera=ILCE-7M3") == {"Milky Way"}


def test_calibration_takes_the_scope(world, admin_client):
    from apps.catalogue.models import CalibrationSet

    for i, (cam, night, filt) in enumerate(
        [
            ("ATR2600M", world["home"], "Ha"),
            ("ILCE-7M3", world["away"], None),
            ("ATR2600M", world["away"], "L"),
        ]
    ):
        CalibrationSet.objects.create(
            type="flat" if filt else "dark",
            camera=cam,
            filter_norm=filt,
            exptime_s=2,
            session_start_utc=T,
            session_end_utc=T,
            night=night,
        )
        Frame.objects.create(
            sha256=f"m{i}".ljust(64, "0"),
            size_bytes=1,
            format="xisf",
            first_seen_at=T,
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.MASTER_FLAT if filt else FrameType.MASTER_DARK,
            camera=cam,
            filter_norm=filt,
            night=night,
            exptime_s=2,
        )

    def sets(qs: str) -> int:
        return len(admin_client.get(f"/api/v1/calibration-sets?{qs}").json())

    def masters(qs: str) -> int:
        return len(admin_client.get(f"/api/v1/masters?{qs}").json())

    assert sets("") == masters("") == 3
    assert sets(f"rig={world['askar'].pk}") == masters(f"rig={world['askar'].pk}") == 2  # the rig's camera
    assert sets("date=2026-02-03") == sets("night=2026-02-03") == 2
    assert masters("date_from=2026-10-01") == 1 and masters("date=2026-02-03&filter=l") == 1
    assert sets("q=dark") == masters("q=dark") == 1
    assert sets("type=flat&camera=atr2600m") == 2
    recal = admin_client.get(f"/api/v1/calibration/recalibration?rig={world['askar'].pk}")
    assert recal.status_code == 200 and recal.json() == []


def test_a_nights_subs_take_the_rest_of_the_scope(world, admin_client):
    url = "/api/v1/nights/2026-10-11/subs?site=54.99,-1.66"
    assert len(admin_client.get(url).json()) == 2
    assert len(admin_client.get(f"{url}&rig={world['sony'].pk}").json()) == 1
    assert len(admin_client.get(f"{url}&target=m 81").json()) == 1


def test_a_card_scoped_to_some_nights_counts_only_their_hours(world, admin_client):
    """Review 2026-10-15: with a date range, a collection card's hours are those nights', not the whole history."""
    from apps.catalogue.models import Dataset

    d0 = world["ds"][0][0]
    Dataset.objects.update(sub_count=1)
    Dataset.objects.filter(pk=d0.pk).update(integration_s=99_999, accepted_integration_s=99_999)
    MachineGrade.objects.filter(frame__dataset=d0).update(verdict="accept")
    cards = admin_client.get("/api/v1/library?date_from=2026-10-01").json()["collections"]
    m81 = next(c for c in cards if c["id"] == world["m81"].pk)
    assert m81["filter_time"]["L"]["total_s"] == 60  # the one sub on 11 Oct, not the dataset's 99,999 s
    assert m81["accepted_integration_s"] == 60
