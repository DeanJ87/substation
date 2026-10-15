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
