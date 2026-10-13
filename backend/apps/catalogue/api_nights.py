"""Nights (T099; contracts/openapi.yaml): a dataset's per-night breakdown, and everything catalogued on one
observing night. No `from __future__ import annotations` here: see substation.api."""

import datetime as dt
from datetime import date, datetime

from django.db.models import Count
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


class NightOut(Schema):
    date: dt.date
    site_key: str
    sites: list[str]
    datasets: list[NightDatasetOut]
    calibration_sets: list[CalibrationSetOut]
    other_frames: dict[str, int]
    previous: dt.date | None
    next: dt.date | None


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
    )
