"""T044: observing night = date(UTC start + longitude/15 h − 12 h) (constitution II, research R8)."""

from datetime import UTC, datetime

import pytest

from apps.ingest.night import observing_night, parse_date_obs, site_key

LON = -1.66262504246919  # owner's site (SITELONG in the spike lights)


@pytest.mark.parametrize(
    ("utc", "night"),
    [
        ("2026-10-07T19:27:58.6301109", "2026-10-07"),  # first light of the evening
        ("2026-10-07T23:59:59", "2026-10-07"),
        ("2026-10-08T00:03:30", "2026-10-07"),  # after local midnight: same night
        ("2026-10-08T04:52:56.2236060", "2026-10-07"),  # last light before dawn
        ("2026-10-08T11:59:00", "2026-10-07"),
        ("2026-10-08T12:10:00", "2026-10-08"),  # local noon (mean solar time) starts the next night
    ],
)
def test_owner_site(utc, night):
    assert observing_night(parse_date_obs(utc), LON).isoformat() == night


def test_far_east_and_west_sites():
    t = parse_date_obs("2026-10-08T02:00:00")
    assert observing_night(t, 150.0).isoformat() == "2026-10-08"  # Australia: 12:00 local on the 8th
    assert observing_night(t, -120.0).isoformat() == "2026-10-07"  # California: 18:00 local on the 7th


def test_parse_date_obs_handles_nina_seven_digit_fractions_and_z():
    assert parse_date_obs("2026-09-28T19:05:02.5708742") == datetime(
        2026, 9, 28, 19, 5, 2, 570874, tzinfo=UTC
    )
    assert parse_date_obs("2026-09-28T19:05:02Z").tzinfo == UTC
    assert parse_date_obs("2026-09-28 19:05:02").hour == 19
    assert parse_date_obs("not a date") is None
    assert parse_date_obs(None) is None


def test_site_key_format():
    assert site_key(54.99516644834888, -1.662625042469193) == "55.00,-1.66"
    assert site_key(None, None) == "unknown"


def test_distance_between_lights_and_masters_site_is_small():
    from apps.ingest.night import SAME_SITE_KM, distance_km

    # SITELAT/SITELONG of the lights vs LAT-OBS/LONG-OBS of the WBPP masters (spike phase 1): same garden
    d = distance_km(54.99516644834888, -1.662625042469193, 54.9929805, -1.6587125)
    assert d < 1.0 < SAME_SITE_KM
    # La Palma (2026-08-15 flats) is a different site
    assert distance_km(54.995, -1.66, 28.774714, -17.9864) > 2000


def test_nearby_sites_share_a_night(db):
    from datetime import date

    from apps.catalogue.services.grouping import night_for

    a = night_for(date(2026, 10, 7), 54.99516644834888, -1.662625042469193)
    b = night_for(date(2026, 10, 7), 54.9929805, -1.6587125)  # rounds differently, 240 m away
    c = night_for(date(2026, 10, 7), 28.774714, -17.9864)
    assert a.pk == b.pk and c.pk != a.pk


def test_parse_date_obs_offsets_and_datetimes():
    from datetime import UTC, datetime

    assert parse_date_obs("2026-09-28T19:05:02.570874+00:00") == datetime(
        2026, 9, 28, 19, 5, 2, 570874, tzinfo=UTC
    )
    assert parse_date_obs("2026-09-28T21:05:02+02:00") == datetime(2026, 9, 28, 19, 5, 2, tzinfo=UTC)
    assert parse_date_obs(datetime(2026, 9, 28, 19, 5, 2, tzinfo=UTC)) == datetime(
        2026, 9, 28, 19, 5, 2, tzinfo=UTC
    )
