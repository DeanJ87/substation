"""The sky as it was shot (spec 015): where each light's target stood at the middle of its exposure, as seen from
where it was taken, plus the Moon and twilight for that night. Worked out with astropy's built-in tables, so no
network is needed; positions are kept (SkyPosition) and only worked out again when an input changes."""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.catalogue.models import Frame

GAP = timedelta(minutes=15)  # subs further apart than this start a new segment of a track (FR-006)


@dataclass
class Pointing:
    ra_deg: float
    dec_deg: float
    source: str  # "solve", "header" or "dataset"


def _offline() -> None:
    from astropy.utils import iers

    # the workers may have no internet; the bundled table is accurate enough for a picture of the sky
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None


def alt_az(
    ra_deg: list[float], dec_deg: list[float], times: list[datetime], lat: float, lon: float
) -> tuple[list[float], list[float], list[float]]:
    """(altitudes, azimuths, hour angles in hours) for each (RA, Dec, time), from one place. No refraction: the
    picture shows geometry, and refraction is under 0.5° above 2° altitude."""
    import numpy as np
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    if not times:
        return [], [], []
    _offline()
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    t = Time(times)
    coords = SkyCoord(ra=np.array(ra_deg) * u.deg, dec=np.array(dec_deg) * u.deg, frame="icrs")
    aa = coords.transform_to(AltAz(obstime=t, location=loc))
    lst = t.sidereal_time("apparent", longitude=lon * u.deg).hour
    ha = ((np.array(lst) - np.array(ra_deg) / 15 + 12) % 24) - 12
    return (
        [round(float(a), 3) for a in np.atleast_1d(aa.alt.deg)],
        [round(float(a), 3) for a in np.atleast_1d(aa.az.deg)],
        [round(float(h), 4) for h in np.atleast_1d(ha)],
    )


def body_track(
    body: str, start: datetime, end: datetime, lat: float, lon: float, step_min: int = 10
) -> list[dict]:
    """The Sun's or Moon's altitude and azimuth every `step_min` minutes."""
    import numpy as np
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, get_body
    from astropy.time import Time

    _offline()
    n = max(int((end - start).total_seconds() // (step_min * 60)) + 1, 2)
    t = Time(np.linspace(Time(start).jd, Time(end).jd, n), format="jd")
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    aa = get_body(body, t, loc).transform_to(AltAz(obstime=t, location=loc))
    return [
        {"time": tt.to_datetime(timezone=UTC), "alt": round(float(a), 2), "az": round(float(z), 2)}
        for tt, a, z in zip(t, aa.alt.deg, aa.az.deg, strict=True)
    ]


def twilight(night_date, lat: float, lon: float) -> dict[str, datetime | None]:  # noqa: ANN001
    """Sunset, astronomical dusk and dawn, and sunrise for the night that starts on `night_date`, found from the
    Sun's altitude every 5 minutes from noon to noon (UTC, shifted by longitude so noon is local)."""
    noon = datetime(night_date.year, night_date.month, night_date.day, 12, tzinfo=UTC) - timedelta(
        hours=lon / 15
    )
    sun = body_track("sun", noon, noon + timedelta(hours=24), lat, lon, step_min=5)

    def crossing(level: float, down: bool) -> datetime | None:
        for a, b in zip(sun, sun[1:], strict=False):
            if (down and a["alt"] >= level > b["alt"]) or (not down and a["alt"] < level <= b["alt"]):
                f = (level - a["alt"]) / (b["alt"] - a["alt"])
                return a["time"] + (b["time"] - a["time"]) * f
        return None

    return {
        "sunset": crossing(0, True),
        "dusk": crossing(-18, True),
        "dawn": crossing(-18, False),
        "sunrise": crossing(0, False),
    }


def moon_phase(when: datetime) -> float:
    import numpy as np
    from astropy.coordinates import get_body, get_sun
    from astropy.time import Time

    _offline()
    t = Time(when)
    return round(float((1 - np.cos(get_sun(t).separation(get_body("moon", t)).rad)) / 2), 3)


def mid_exposure(f: Frame) -> datetime | None:
    if f.date_obs_utc is None:
        return None
    return f.date_obs_utc + timedelta(seconds=(f.exptime_s or 0) / 2)


def pointing(f: Frame, header: dict, fallback: dict[int, Pointing | None]) -> Pointing | None:
    """The plate solution's centre, else the header's RA/Dec, else the dataset's usual pointing (FR-003)."""
    solve = getattr(f, "solve", None)
    if solve is not None and solve.ra_deg is not None and solve.dec_deg is not None:
        return Pointing(solve.ra_deg, solve.dec_deg, "solve")
    ra, dec = header.get("RA"), header.get("DEC")
    try:
        if ra is not None and dec is not None:
            return Pointing(float(ra), float(dec), "header")
    except (TypeError, ValueError):
        pass
    if f.dataset_id is None or f.dataset is None:
        return None
    if f.dataset_id not in fallback:
        from apps.catalogue.services.library import centre

        c = centre(f.dataset)
        fallback[f.dataset_id] = Pointing(c[0], c[1], "dataset") if c else None
    return fallback[f.dataset_id]


def positions(frames: Iterable[Frame], lat: float, lon: float, headers: dict[str, dict]) -> dict[str, object]:
    """Each frame's SkyPosition, worked out (in one batch) for any that are new or whose inputs changed."""
    from apps.processing.models import SkyPosition

    frames = list(frames)
    kept = {p.frame_id: p for p in SkyPosition.objects.filter(frame__in=frames)}
    fallback: dict[int, Pointing | None] = {}
    todo: list[tuple[Frame, Pointing, datetime]] = []
    out: dict[str, object] = {}
    for f in frames:
        at = mid_exposure(f)
        p = pointing(f, headers.get(f.pk, {}), fallback)
        if at is None or p is None:
            continue
        k = kept.get(f.pk)
        same = k is not None and (k.at, k.site_lat, k.site_lon, k.ra_deg, k.dec_deg, k.source) == (
            at,
            lat,
            lon,
            p.ra_deg,
            p.dec_deg,
            p.source,
        )
        if same:
            out[f.pk] = k
        else:
            todo.append((f, p, at))
    if todo:
        alts, azs, has = alt_az(
            [p.ra_deg for _, p, _ in todo],
            [p.dec_deg for _, p, _ in todo],
            [at for _, _, at in todo],
            lat,
            lon,
        )
        for (f, p, at), alt, az, ha in zip(todo, alts, azs, has, strict=True):
            row, _ = SkyPosition.objects.update_or_create(
                frame=f,
                defaults={
                    "at": at,
                    "site_lat": lat,
                    "site_lon": lon,
                    "ra_deg": p.ra_deg,
                    "dec_deg": p.dec_deg,
                    "source": p.source,
                    "alt_deg": alt,
                    "az_deg": az,
                    "hour_angle_h": ha,
                },
            )
            out[f.pk] = row
    return out


def segments(times: list[datetime], hour_angles: list[float]) -> list[int]:
    """A segment number per sub of one track (in time order): a new segment after a gap of more than 15 minutes,
    or where the target crossed the meridian (a flip), so the line isn't drawn across either (FR-006)."""
    seg, out = 0, []
    for i, t in enumerate(times):
        if i and (t - times[i - 1] > GAP or (hour_angles[i - 1] < 0 <= hour_angles[i])):
            seg += 1
        out.append(seg)
    return out


def target_curve(ra: float, dec: float, start: datetime, end: datetime, lat: float, lon: float) -> list[dict]:
    """A target's altitude through the night every 10 minutes, for the altitude chart."""
    n = max(int((end - start).total_seconds() // 600) + 1, 2)
    times = [start + (end - start) * i / (n - 1) for i in range(n)]
    alts, azs, _ = alt_az([ra] * n, [dec] * n, times, lat, lon)
    return [{"time": t, "alt": a, "az": z} for t, a, z in zip(times, alts, azs, strict=True)]


def median_pointing(rows: list) -> tuple[float, float]:
    """The middle of a target's pointings; RA is taken around the circle, so 359° and 1° give 0°, not 180°."""
    ras = [r.ra_deg for r in rows]
    if max(ras) - min(ras) > 180:
        ras = [(r + 180) % 360 - 180 for r in ras]
    return statistics.median(ras) % 360, statistics.median(r.dec_deg for r in rows)
