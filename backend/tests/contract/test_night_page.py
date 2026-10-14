"""Spec 012: the night page knows where the night was shot, the Moon, and every sub that night in time order."""

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, Night

pytestmark = pytest.mark.django_db


def test_night_has_place_moon_and_subs(admin_client):
    n = Night.objects.create(date=date(2026, 9, 25), site_key="home")
    ds = Dataset.objects.create(
        group_key="k", display_name="NGC 7635 · Ha", target="NGC 7635", filter_norm="Ha"
    )
    start = datetime(2026, 9, 25, 21, tzinfo=UTC)
    for i in range(3):
        Frame.objects.create(
            sha256=f"{i:064x}",
            frame_type="light",
            status=FrameStatus.CATALOGUED,
            night=n,
            dataset=ds,
            date_obs_utc=start + timedelta(hours=i),
            site_lat=53.0,
            site_lon=-1.5,
            size_bytes=1,
            format="fits",
            first_seen_at=start,
        )
    r = admin_client.get("/api/v1/nights/2026-09-25").json()
    assert r["lat"] == 53.0 and r["lon"] == -1.5
    assert 0 <= r["moon"]["illumination"] <= 1 and r["moon"]["altitude_deg"] is not None
    subs = admin_client.get("/api/v1/nights/2026-09-25/subs?site=home").json()
    assert [x["sha256"] for x in subs] == [f"{i:064x}" for i in range(3)]
    assert {x["dataset_id"] for x in subs} == {ds.pk}
