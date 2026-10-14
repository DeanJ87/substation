"""Nights (T099; contracts/openapi.yaml): a dataset's per-night breakdown, and everything catalogued on one
observing night. No `from __future__ import annotations` here: see substation.api."""

import datetime as dt
from datetime import date, datetime

from django.db.models import Avg, Count, Max, Min
from django.shortcuts import get_object_or_404

from substation.api import ApiError, Schema

from .api import DatasetOut, dataset_out, router
from .api_calibration import CalibrationSetOut, list_calibration_sets
from .models import Dataset, DatasetNight, Frame, FrameStatus, Night


class DatasetNightOut(Schema):
    night: date
    sub_count: int
    integration_s: float
    user_rejected_count: int
    first_utc: datetime | None
    last_utc: datetime | None


class NightDatasetOut(DatasetNightOut):
    dataset: DatasetOut


class MoonOut(Schema):
    illumination: float  # 0 new to 1 full
    altitude_deg: float | None  # at the middle of the night's lights, where the place is known
    up_during_lights: bool | None


class NightOut(Schema):
    date: dt.date
    site_key: str
    sites: list[str]
    datasets: list[NightDatasetOut]
    calibration_sets: list[CalibrationSetOut]
    other_frames: dict[str, int]
    previous: dt.date | None
    next: dt.date | None
    lat: float | None = None  # where the night's subs were shot (spec 012), for the map and the Moon
    lon: float | None = None
    first_utc: datetime | None = None
    last_utc: datetime | None = None
    moon: MoonOut | None = None


def moon_at(when: datetime, lat: float | None, lon: float | None, until: datetime | None = None) -> MoonOut:
    """The Moon's phase, and its altitude at `when` (and whether it rose above the horizon before `until`), from
    astropy's built-in ephemeris: no network needed."""
    import numpy as np
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, get_body, get_sun
    from astropy.time import Time
    from astropy.utils import iers

    # the workers may have no internet; the bundled table is accurate enough here
    iers.conf.auto_download = False
    t = Time(when)
    moon, sun = get_body("moon", t), get_sun(t)
    lit = float((1 - np.cos(sun.separation(moon).rad)) / 2)
    if lat is None or lon is None:
        return MoonOut(illumination=round(lit, 3), altitude_deg=None, up_during_lights=None)
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    times = Time(when) if until is None else Time(np.linspace(Time(when).jd, Time(until).jd, 12), format="jd")
    alts = get_body("moon", times, loc).transform_to(AltAz(obstime=times, location=loc)).alt.deg
    alts = np.atleast_1d(alts)
    mid = float(alts[len(alts) // 2])
    return MoonOut(
        illumination=round(lit, 3), altitude_deg=round(mid, 1), up_during_lights=bool((alts > 0).any())
    )


def _dn(dn: DatasetNight) -> dict:
    return {
        "night": dn.night.date,
        "sub_count": dn.sub_count,
        "integration_s": dn.integration_s,
        "user_rejected_count": dn.user_rejected_count,
        "first_utc": dn.first_utc,
        "last_utc": dn.last_utc,
    }


@router.get("/datasets/{id}/nights", response=list[DatasetNightOut])
def dataset_nights(request, id: int):  # noqa: A002
    ds = get_object_or_404(Dataset, pk=id)
    return [_dn(dn) for dn in ds.nights.select_related("night").order_by("-night__date")]


@router.get("/nights/{date}", response=NightOut)
def night(request, date: date, site: str | None = None):  # noqa: A002
    nights = Night.objects.filter(date=date)
    sites = sorted(nights.values_list("site_key", flat=True))
    if not sites:
        raise ApiError(404, "not_found", f"Nothing catalogued on {date:%-d %B %Y}.")
    if site is None:  # the site with the most frames that night
        site = max(sites, key=lambda k: Frame.objects.filter(night__date=date, night__site_key=k).count())
    n = get_object_or_404(Night, date=date, site_key=site)
    dns = DatasetNight.objects.filter(night=n).select_related("night", "dataset").order_by("first_utc")
    sets = [cs for cs in list_calibration_sets(request, night=date)]
    other = dict(
        Frame.objects.filter(night=n, dataset__isnull=True, calibration_set__isnull=True)
        .exclude(status=FrameStatus.IGNORED)
        .values_list("frame_type")
        .annotate(c=Count("sha256"))
    )
    lights = Frame.objects.filter(night=n, frame_type="light", status=FrameStatus.CATALOGUED).aggregate(
        lat=Avg("site_lat"), lon=Avg("site_lon"), first=Min("date_obs_utc"), last=Max("date_obs_utc")
    )
    moon = None
    if lights["first"]:
        mid = lights["first"] + (lights["last"] - lights["first"]) / 2
        try:
            moon = moon_at(mid, lights["lat"], lights["lon"]) if lights["first"] == lights["last"] else None
            moon = moon or moon_at(lights["first"], lights["lat"], lights["lon"], until=lights["last"])
        except Exception:  # noqa: BLE001 - the Moon is a nicety; a night page never fails for it
            moon = None
    all_dates = Night.objects.filter(site_key=site).order_by("date").values_list("date", flat=True)
    prev = all_dates.filter(date__lt=date).last()
    nxt = all_dates.filter(date__gt=date).first()
    return NightOut(
        date=date,
        site_key=site,
        sites=sites,
        datasets=[NightDatasetOut(**_dn(dn), dataset=dataset_out(dn.dataset)) for dn in dns],
        calibration_sets=sets,
        other_frames=other,
        previous=prev,
        next=nxt,
        lat=lights["lat"],
        lon=lights["lon"],
        first_utc=lights["first"],
        last_utc=lights["last"],
        moon=moon,
    )
