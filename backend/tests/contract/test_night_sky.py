"""Spec 015: a night's sky — every light where its target stood, tracks per target and rig, the Moon and twilight."""

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, HeaderSnapshot, Night, Rig
from apps.processing import sky
from apps.processing.models import PlateSolve, SkyPosition

pytestmark = pytest.mark.django_db

NEWCASTLE = (54.995, -1.663)


def _hand_alt_az(ra: float, dec: float, when: datetime, lat: float, lon: float) -> tuple[float, float]:
    """The textbook way: Greenwich mean sidereal time, hour angle, then the spherical triangle. No precession or
    nutation, so it differs from astropy by a few tenths of a degree in 2026; SC-003 allows half a degree."""
    jd = when.timestamp() / 86400 + 2440587.5
    gmst = (18.697374558 + 24.06570982441908 * (jd - 2451545.0)) % 24
    ha = math.radians(((gmst + lon / 15) * 15 - ra) % 360)
    phi, d = math.radians(lat), math.radians(dec)
    alt = math.asin(math.sin(d) * math.sin(phi) + math.cos(d) * math.cos(phi) * math.cos(ha))
    az = math.atan2(
        -math.sin(ha) * math.cos(d), math.cos(phi) * math.sin(d) - math.sin(phi) * math.cos(d) * math.cos(ha)
    )
    return math.degrees(alt), math.degrees(az) % 360


@pytest.mark.parametrize(
    ("ra", "dec", "when"),
    [
        (279.2347, 38.7837, datetime(2026, 10, 11, 21, 0, tzinfo=UTC)),  # Vega, high in the west
        (83.8221, -5.3911, datetime(2026, 10, 12, 3, 30, tzinfo=UTC)),  # M 42, low in the south-east
        (314.75, 44.3, datetime(2026, 10, 11, 23, 0, tzinfo=UTC)),  # North America Nebula
    ],
)
def test_positions_match_a_hand_calculation_within_half_a_degree(ra, dec, when):
    alts, azs, has = sky.alt_az([ra], [dec], [when], *NEWCASTLE)
    alt, az = _hand_alt_az(ra, dec, when, *NEWCASTLE)
    assert abs(alts[0] - alt) < 0.5
    assert abs((azs[0] - az + 180) % 360 - 180) < 0.5
    assert -12 <= has[0] <= 12


def test_a_track_breaks_at_a_gap_and_at_the_meridian():
    t0 = datetime(2026, 10, 11, 22, tzinfo=UTC)
    times = [
        t0,
        t0 + timedelta(minutes=5),
        t0 + timedelta(minutes=40),
        t0 + timedelta(minutes=45),
        t0 + timedelta(minutes=50),
    ]
    assert sky.segments(times, [-1.0, -0.9, -0.3, -0.05, 0.02]) == [0, 0, 1, 1, 2]


def test_twilight_for_newcastle_in_october():
    tw = sky.twilight(date(2026, 10, 11), *NEWCASTLE)
    assert tw["sunset"] and tw["dusk"] and tw["dawn"] and tw["sunrise"]
    assert tw["sunset"] < tw["dusk"] < tw["dawn"] < tw["sunrise"]
    assert 16 <= tw["sunset"].hour <= 18  # about 17:20 UTC
    assert 18 <= tw["dusk"].hour <= 20


def _light(i, n, ds, when, *, solve=None, header=None):
    f = Frame.objects.create(
        sha256=f"{i:064x}",
        frame_type="light",
        status=FrameStatus.CATALOGUED,
        night=n,
        dataset=ds,
        date_obs_utc=when,
        exptime_s=300,
        site_lat=NEWCASTLE[0],
        site_lon=NEWCASTLE[1],
        size_bytes=1,
        format="fits",
        first_seen_at=when,
    )
    if solve:
        PlateSolve.objects.create(frame=f, state="solved", ra_deg=solve[0], dec_deg=solve[1])
    if header:
        HeaderSnapshot.objects.create(
            frame=f, image_index=0, keywords={k: {"value": v} for k, v in header.items()}
        )
    return f


def test_night_sky_has_tracks_per_target_and_rig(admin_client):
    n = Night.objects.create(
        date=date(2026, 10, 11), site_key="home", site_lat=NEWCASTLE[0], site_lon=NEWCASTLE[1]
    )
    askar = Rig.objects.create(key="a", name="Askar 71F + ATR2600M")
    sony = Rig.objects.create(key="b", name="Sony A7 III")
    nan = Dataset.objects.create(
        group_key="1", display_name="NGC 7000", target="NGC 7000", filter_norm="OIII", rig=askar
    )
    heart = Dataset.objects.create(
        group_key="2", display_name="IC 1805", target="IC 1805", filter_norm="L", rig=sony
    )
    t0 = datetime(2026, 10, 11, 21, tzinfo=UTC)
    for i in range(3):
        _light(i, n, nan, t0 + timedelta(minutes=6 * i), solve=(314.75, 44.3))
    _light(3, n, heart, t0, header={"RA": 38.2, "DEC": 61.45})
    _light(4, n, heart, t0 + timedelta(minutes=6), header={"RA": 38.2, "DEC": 61.45})
    nowhere = _light(5, n, heart, t0 + timedelta(hours=1))
    nowhere.date_obs_utc = None
    nowhere.save()

    r = admin_client.get("/api/v1/nights/2026-10-11/sky?site=home").json()
    assert {t["label"] for t in r["tracks"]} == {"NGC 7000 · OIII", "IC 1805 · L"}
    assert {g["name"] for g in r["rigs"]} == {"Askar 71F + ATR2600M", "Sony A7 III"}
    assert len(r["subs"]) == 5 and [u["sha256"] for u in r["unplaced"]] == [f"{5:064x}"]
    sources = {s["sha256"][-1]: s["source"] for s in r["subs"]}
    assert sources["0"] == "solve" and sources["3"] == "header"
    first = next(s for s in r["subs"] if s["sha256"] == f"{0:064x}")
    assert first["time"].startswith("2026-10-11T21:02:30")  # middle of a 300 s exposure
    assert 0 < first["alt"] < 90
    assert r["twilight"]["dusk"] and r["moon"]["points"] and 0 <= r["moon"]["illumination"] <= 1
    assert all(len(t["curve"]) > 2 for t in r["targets"])
    assert r["start"] < r["subs"][0]["time"]

    # kept, not worked out again; a new plate solve moves the point
    assert SkyPosition.objects.count() == 5
    PlateSolve.objects.create(frame_id=f"{3:064x}", state="solved", ra_deg=40.0, dec_deg=61.0)
    r2 = admin_client.get("/api/v1/nights/2026-10-11/sky?site=home").json()
    moved = next(s for s in r2["subs"] if s["sha256"] == f"{3:064x}")
    assert moved["source"] == "solve"
    assert SkyPosition.objects.get(frame_id=f"{3:064x}").ra_deg == 40.0


def test_night_sky_without_a_place_lists_everything_as_unplaced(admin_client):
    n = Night.objects.create(date=date(2026, 10, 12), site_key="unknown")
    ds = Dataset.objects.create(group_key="1", display_name="M 31", target="M 31", filter_norm="L")
    f = _light(0, n, ds, datetime(2026, 10, 12, 22, tzinfo=UTC))
    Frame.objects.filter(pk=f.pk).update(site_lat=None, site_lon=None)
    r = admin_client.get("/api/v1/nights/2026-10-12/sky?site=unknown").json()
    assert r["subs"] == [] and r["unplaced"][0]["reason"] == "Where it was shot isn't known."
