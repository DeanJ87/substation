"""A target across all its nights, from one place (spec 015 N7): every light where its target stood, tracks stacked
by night, and each night's span of altitude for a strip under the dome. Positions come from the same SkyPosition
cache as the night view. On the catalogue router. No `from __future__ import annotations` here: see substation.api."""

import statistics
from collections import defaultdict
from datetime import date, datetime

from django.shortcuts import get_object_or_404

from apps.catalogue.api import router
from apps.catalogue.models import Collection, Dataset, Frame, FrameStatus, FrameType
from substation.api import Schema

from . import sky
from .api import _kw
from .api_sky import SkyFov, SkyRig, _rig_of, fov_of, night_places
from .effective import effective


class NightsPlace(Schema):
    key: str  # the nights' site key
    lat: float
    lon: float
    subs: int
    nights: int


class NightsNight(Schema):
    date: date
    site_key: str
    subs: int
    integration_s: float
    first: datetime
    last: datetime
    alt_min: float
    alt_max: float
    alt_mid: float  # the median sub's altitude


class NightsSub(Schema):
    sha256: str
    time: datetime
    alt: float
    az: float
    night: int  # index into nights, oldest first
    dataset_id: int
    segment: int  # tracks break at gaps and meridian flips, within a night and dataset
    rig: str  # key into rigs
    verdict: str | None


class NightsOut(Schema):
    name: str
    site_key: str | None  # the place shown
    lat: float | None
    lon: float | None
    places: list[NightsPlace]  # every place this target was shot from, most subs first
    nights: list[NightsNight]
    rigs: list[SkyRig]
    subs: list[NightsSub]
    unplaced: int  # lights from this place that couldn't be put on the sky
    fov: SkyFov | None  # the most-shot rig's field of view, for a frame on the dome


def _frames(**where: object) -> list:  # of Frame, its night and dataset always set
    return list(
        Frame.objects.filter(
            frame_type=FrameType.LIGHT,
            status=FrameStatus.CATALOGUED,
            night__isnull=False,
            dataset__isnull=False,
            **where,
        )
        .select_related("dataset__rig", "night", "grade", "solve")
        .prefetch_related("verdicts", "headers")
        .order_by("date_obs_utc")
    )


def _places(frames: list) -> list[NightsPlace]:
    by_key: dict[str, list] = defaultdict(list)
    for f in frames:
        by_key[f.night.site_key].append(f)
    nights = {f.night.pk: f.night for f in frames}
    where = night_places(list(nights.values()))
    out = []
    for key, fs in by_key.items():
        spots = [where[n] for n in {f.night_id for f in fs} if n in where]
        if not spots:
            continue
        out.append(
            NightsPlace(
                key=key,
                lat=round(statistics.fmean(p[0] for p in spots), 5),
                lon=round(statistics.fmean(p[1] for p in spots), 5),
                subs=len(fs),
                nights=len(spots),
            )
        )
    return sorted(out, key=lambda p: -p.subs)


def across_nights(name: str, frames: list, site: str | None) -> NightsOut:
    places = _places(frames)
    chosen = next((p for p in places if p.key == site), places[0] if places else None)
    out = NightsOut(
        name=name,
        site_key=chosen.key if chosen else None,
        lat=chosen.lat if chosen else None,
        lon=chosen.lon if chosen else None,
        places=places,
        nights=[],
        rigs=[],
        subs=[],
        unplaced=0,
        fov=None,
    )
    if not chosen:
        return out
    here = [f for f in frames if f.night.site_key == chosen.key]
    where = night_places(list({f.night.pk: f.night for f in here}.values()))
    here = [f for f in here if f.night_id in where]
    placed = sky.positions_at(here, lambda f: where[f.night_id or 0], {f.pk: _kw(f) for f in here})
    out.unplaced = len(here) - len(placed)
    _fill(out, [f for f in here if f.pk in placed], placed)
    busiest = max(out.rigs, key=lambda r: sum(s.rig == r.key for s in out.subs), default=None)
    if busiest:
        ds = next(f.dataset for f in here if _rig_of(f.dataset)[0] == busiest.key)
        out.fov = fov_of([f for f in here if f.dataset_id == ds.pk], ds)
    return out


def _fill(out: NightsOut, frames: list, placed: dict) -> None:
    by_night: dict[date, list] = defaultdict(list)
    for f in frames:
        by_night[f.night.date].append(f)
    rigs: dict[str, str] = {}
    for i, (d, fs) in enumerate(sorted(by_night.items())):
        rows = [placed[f.pk] for f in fs]
        alts = [r.alt_deg for r in rows]
        out.nights.append(
            NightsNight(
                date=d,
                site_key=fs[0].night.site_key,
                subs=len(fs),
                integration_s=sum(f.exptime_s or 0 for f in fs),
                first=min(r.at for r in rows),
                last=max(r.at for r in rows),
                alt_min=min(alts),
                alt_max=max(alts),
                alt_mid=statistics.median(alts),
            )
        )
        by_ds: dict[int, list] = defaultdict(list)
        for f in fs:
            by_ds[f.dataset_id].append(f)
        for ds_frames in by_ds.values():
            ds_rows = [placed[f.pk] for f in ds_frames]
            segs = sky.segments([r.at for r in ds_rows], [r.hour_angle_h for r in ds_rows])
            for f, r, seg in zip(ds_frames, ds_rows, segs, strict=True):
                rkey, rname = _rig_of(f.dataset)
                rigs[rkey] = rname
                e = effective(f, list(f.verdicts.all()), getattr(f, "grade", None))
                out.subs.append(
                    NightsSub(
                        sha256=f.pk,
                        time=r.at,
                        alt=r.alt_deg,
                        az=r.az_deg,
                        night=i,
                        dataset_id=f.dataset_id,
                        segment=seg,
                        rig=rkey,
                        verdict=e.verdict,
                    )
                )
    out.rigs = [SkyRig(key=k, name=v) for k, v in rigs.items()]
    out.subs.sort(key=lambda s: s.time)


@router.get("/datasets/{dataset_id}/sky", response=NightsOut)
def dataset_sky(request, dataset_id: int, site: str | None = None):
    """One dataset's lights across all its nights, from one place (the one with most subs unless `site` says)."""
    ds = get_object_or_404(Dataset, pk=dataset_id)
    return across_nights(ds.display_name or ds.target, _frames(dataset=ds), site)


@router.get("/collections/{collection_id}/sky", response=NightsOut)
def collection_sky(request, collection_id: int, site: str | None = None):
    """Every light of a collection across all its nights, from one place."""
    c = get_object_or_404(Collection, pk=collection_id)
    name = c.name.split(" - ", 1)[1] if " - " in c.name else c.name
    return across_nights(name, _frames(dataset__collection=c), site)
