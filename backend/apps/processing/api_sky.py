"""The night's sky (spec 015): every light where its target stood when it was taken, tracks per target and rig, the
Moon and twilight. On the catalogue router. No `from __future__ import annotations` here: see substation.api."""

from datetime import date, datetime, timedelta

from django.db.models import Avg
from django.shortcuts import get_object_or_404

from apps.catalogue.api import router
from apps.catalogue.models import Frame, FrameStatus, FrameType, Night
from substation.api import Schema

from . import sky
from .api import _file, _kw
from .effective import effective


class SkyPoint(Schema):
    time: datetime
    alt: float
    az: float


class SkySub(Schema):
    sha256: str
    file: str
    time: datetime  # middle of the exposure
    exptime_s: float | None
    alt: float
    az: float
    source: str  # where the pointing came from: solve, header or dataset
    track: int  # index into tracks
    segment: int  # tracks break at gaps and meridian flips
    verdict: str | None
    weight: float
    fwhm_arcsec: float | None
    fwhm_px: float | None


class SkyTrack(Schema):
    target: str  # key into targets
    rig: str  # key into rigs
    dataset_id: int
    filter: str
    label: str  # "Heart Nebula · Panel 1 · OIII"
    first: datetime
    last: datetime
    subs: int
    integration_s: float


class SkyTarget(Schema):
    key: str
    name: str
    collection_id: int | None
    curve: list[SkyPoint]  # altitude through the night, for the chart


class SkyRig(Schema):
    key: str
    name: str


class SkyUnplaced(Schema):
    sha256: str
    file: str
    reason: str


class SkyMoon(Schema):
    illumination: float
    points: list[SkyPoint]


class SkyTwilight(Schema):
    sunset: datetime | None
    dusk: datetime | None  # astronomical: the Sun 18° below the horizon
    dawn: datetime | None
    sunrise: datetime | None


class SkyOut(Schema):
    date: date
    site_key: str
    lat: float | None
    lon: float | None
    start: datetime | None  # the span the chart and the slider cover
    end: datetime | None
    twilight: SkyTwilight | None
    moon: SkyMoon | None
    targets: list[SkyTarget]
    rigs: list[SkyRig]
    tracks: list[SkyTrack]
    subs: list[SkySub]
    unplaced: list[SkyUnplaced]


def _target_of(ds) -> tuple[str, str, int | None]:  # noqa: ANN001
    """(key, name, collection id): the collection's common name when it has one, else the dataset's target."""
    if ds.collection_id and ds.collection:
        name = ds.collection.name
        return f"c{ds.collection_id}", name.split(" - ", 1)[1] if " - " in name else name, ds.collection_id
    return f"t:{ds.target}", ds.target or "Unknown target", None


def _rig_of(ds) -> tuple[str, str]:  # noqa: ANN001
    if ds.rig_id and ds.rig:
        return f"r{ds.rig_id}", ds.rig.name
    name = " + ".join(p for p in (ds.telescope, ds.camera) if p) or "Unknown rig"
    return f"n:{name}", name


def _track_label(ds, target: str) -> str:  # noqa: ANN001
    parts = [target, f"Panel {ds.panel}" if ds.panel is not None else "", ds.filter_norm]
    return " · ".join(p for p in parts if p)


def _span(firsts: list[datetime], tw: dict | None) -> tuple[datetime, datetime]:
    """From dusk (or the first sub, if earlier) to dawn (or the last sub, if later), with a little either side."""
    start, end = min(firsts), max(firsts)
    if tw and tw.get("dusk") and tw.get("dawn"):
        start, end = min(start, tw["dusk"]), max(end, tw["dawn"])
    pad = timedelta(minutes=20)
    return start - pad, end + pad


@router.get("/nights/{date}/sky", response=SkyOut)
def night_sky(request, date: date, site: str):  # noqa: A002
    n = get_object_or_404(Night, date=date, site_key=site)
    frames = list(
        Frame.objects.filter(
            night=n, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED, dataset__isnull=False
        )
        .select_related("dataset__rig", "dataset__collection", "measurement", "grade", "solve")
        .prefetch_related("verdicts", "copies", "headers")
        .order_by("date_obs_utc")
    )
    where = Frame.objects.filter(pk__in=[f.pk for f in frames]).aggregate(
        lat=Avg("site_lat"), lon=Avg("site_lon")
    )
    lat = where["lat"] if where["lat"] is not None else n.site_lat
    lon = where["lon"] if where["lon"] is not None else n.site_lon
    empty = SkyOut(
        date=date,
        site_key=site,
        lat=lat,
        lon=lon,
        start=None,
        end=None,
        twilight=None,
        moon=None,
        targets=[],
        rigs=[],
        tracks=[],
        subs=[],
        unplaced=[],
    )
    if lat is None or lon is None:
        empty.unplaced = [
            SkyUnplaced(sha256=f.pk, file=_file(f), reason="Where it was shot isn't known.") for f in frames
        ]
        return empty
    headers = {f.pk: _kw(f) for f in frames}
    placed = sky.positions(frames, lat, lon, headers)
    return _build(empty, date, frames, placed, lat, lon)


def _build(out: SkyOut, night_date: date, frames: list, placed: dict, lat: float, lon: float) -> SkyOut:
    targets: dict[str, dict] = {}
    rigs: dict[str, str] = {}
    track_index: dict[int, int] = {}
    tracks: list[dict] = []
    for f in frames:
        if f.pk not in placed:
            why = (
                "No time recorded."
                if f.date_obs_utc is None
                else "No pointing: not plate solved and no RA/Dec."
            )
            out.unplaced.append(SkyUnplaced(sha256=f.pk, file=_file(f), reason=why))
            continue
        ds = f.dataset
        tkey, tname, cid = _target_of(ds)
        rkey, rname = _rig_of(ds)
        targets.setdefault(tkey, {"name": tname, "collection_id": cid, "rows": []})["rows"].append(
            placed[f.pk]
        )
        rigs[rkey] = rname
        if ds.pk not in track_index:
            track_index[ds.pk] = len(tracks)
            tracks.append(
                {"ds": ds, "target": tkey, "rig": rkey, "label": _track_label(ds, tname), "frames": []}
            )
        tracks[track_index[ds.pk]]["frames"].append(f)
    if not tracks:
        return out
    tw = sky.twilight(night_date, lat, lon)
    start, end = _span([placed[f.pk].at for t in tracks for f in t["frames"]], tw)
    out.start, out.end = start, end
    out.twilight = SkyTwilight(**tw)
    out.moon = SkyMoon(
        illumination=sky.moon_phase(start + (end - start) / 2),
        points=[SkyPoint(**p) for p in sky.body_track("moon", start, end, lat, lon)],
    )
    out.targets = [
        SkyTarget(
            key=k,
            name=v["name"],
            collection_id=v["collection_id"],
            curve=[
                SkyPoint(**p) for p in sky.target_curve(*sky.median_pointing(v["rows"]), start, end, lat, lon)
            ],
        )
        for k, v in targets.items()
    ]
    out.rigs = [SkyRig(key=k, name=v) for k, v in rigs.items()]
    for i, t in enumerate(tracks):
        rows = [placed[f.pk] for f in t["frames"]]
        segs = sky.segments([r.at for r in rows], [r.hour_angle_h for r in rows])
        for f, r, seg in zip(t["frames"], rows, segs, strict=True):
            out.subs.append(_sub(f, r, i, seg))
        out.tracks.append(
            SkyTrack(
                target=t["target"],
                rig=t["rig"],
                dataset_id=t["ds"].pk,
                filter=t["ds"].filter_norm,
                label=t["label"],
                first=rows[0].at,
                last=rows[-1].at,
                subs=len(rows),
                integration_s=sum(f.exptime_s or 0 for f in t["frames"]),
            )
        )
    out.subs.sort(key=lambda s: s.time)
    return out


def _sub(f: Frame, r, track: int, segment: int) -> SkySub:  # noqa: ANN001
    m = getattr(f, "measurement", None)
    g = getattr(f, "grade", None)
    e = effective(f, list(f.verdicts.all()), g)
    return SkySub(
        sha256=f.pk,
        file=_file(f),
        time=r.at,
        exptime_s=f.exptime_s,
        alt=r.alt_deg,
        az=r.az_deg,
        source=r.source,
        track=track,
        segment=segment,
        verdict=e.verdict,
        weight=e.weight,
        fwhm_arcsec=m.fwhm_arcsec if m else None,
        fwhm_px=m.fwhm_px if m else None,
    )
