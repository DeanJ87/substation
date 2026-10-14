"""Spec 012: the map groups lights by where they were shot, with nights and a picture per place."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, Night

pytestmark = pytest.mark.django_db


def _light(sha: str, lat: float, lon: float, night: Night, ds: Dataset, status: str = "catalogued") -> None:
    Frame.objects.create(
        sha256=sha * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=datetime.now(UTC),
        status=status,
        frame_type="light",
        site_lat=lat,
        site_lon=lon,
        night=night,
        dataset=ds,
        target=ds.target,
    )


def test_places_group_nearby_lights(admin_client):
    ds = Dataset.objects.create(group_key="k", display_name="M 31 · L", target="M 31", filter_norm="L")
    home1 = Night.objects.create(site_key="55.0,-1.7", date=date(2026, 9, 25))
    home2 = Night.objects.create(site_key="55.0,-1.7", date=date(2026, 9, 26))
    away = Night.objects.create(site_key="-8.5,119.9", date=date(2026, 7, 1))
    _light("a", 55.0012, -1.6651, home1, ds)
    _light("b", 55.0014, -1.6649, home2, ds)
    _light("c", -8.4961, 119.8872, away, ds)
    _light("d", -8.4961, 119.8872, away, ds, status="binned")
    places = admin_client.get("/api/v1/map").json()["places"]
    assert [p["subs"] for p in places] == [2, 1]
    home = places[0]
    assert home["first"] == "2026-09-25" and home["last"] == "2026-09-26"
    assert [n["date"] for n in home["nights"]] == ["2026-09-26", "2026-09-25"]
    assert home["targets"] == ["M 31"] and home["image"].endswith("/glance")
