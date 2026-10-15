"""The night's sky (spec 015): every light where its target stood when it was taken, tracks per target and rig, the
Moon and twilight. On the catalogue router. No `from __future__ import annotations` here: see substation.api."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from django.db.models import Avg
from django.shortcuts import get_object_or_404

from apps.catalogue.api import router
from apps.catalogue.models import Frame, FrameStatus, FrameType, Night
from substation.api import Schema

from . import sky
from .api import _file, _kw
from .effective import effective

log = logging.getLogger("substation.sky")


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


class SkyFov(Schema):
    """The rig's field of view as plate solved (spec 015 amendment): centre, size and rotation, so the dome can draw
    what the camera framed."""

    ra_deg: float
    dec_deg: float
    w_deg: float
    h_deg: float
    rotation_deg: float  # the image's up direction, east of north, folded onto 0–180


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
    fov: SkyFov | None = None


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


def night_places(nights: list[Night]) -> dict[int, tuple[float, float]]:
    """Each night's place: the mean of its catalogued lights' recorded sites, else the night's own (015-DR-02). The
    night view and the across-nights view use the same place, so a light's kept position serves both."""
    rows = (
        Frame.objects.filter(
            night__in=nights, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED, dataset__isnull=False
        )
        .values("night_id")
        .annotate(lat=Avg("site_lat"), lon=Avg("site_lon"))
    )
    mean = {r["night_id"]: (r["lat"], r["lon"]) for r in rows}
    out: dict[int, tuple[float, float]] = {}
    for n in nights:
        lat, lon = mean.get(n.pk, (None, None))
        lat = lat if lat is not None else n.site_lat
        lon = lon if lon is not None else n.site_lon
        if lat is not None and lon is not None:
            out[n.pk] = (lat, lon)
    return out


def fov_of(frames: list, ds) -> SkyFov | None:  # noqa: ANN001
    """The dataset's field of view from its plate solves: those among `frames` if any carry a size, else up to 200
    of the dataset's others."""
    solves = [
        s
        for f in frames
        if (s := getattr(f, "solve", None)) is not None
        and s.fov_w_deg
        and s.fov_h_deg
        and s.ra_deg is not None
    ]
    if not solves:
        from .models import PlateSolve

        solves = list(
            PlateSolve.objects.filter(
                frame__dataset=ds, fov_w_deg__isnull=False, fov_h_deg__isnull=False, ra_deg__isnull=False
            )[:200]
        )
    if not solves:
        return None
    import statistics

    ra, dec = sky.median_pointing(solves)
    return SkyFov(
        ra_deg=round(ra, 5),
        dec_deg=round(dec, 5),
        w_deg=round(statistics.median(s.fov_w_deg for s in solves), 4),
        h_deg=round(statistics.median(s.fov_h_deg for s in solves), 4),
        rotation_deg=sky.frame_rotation(
            [s.rotation_deg for s in solves if s.rotation_deg is not None] or [0]
        ),
    )


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
    place = night_places([n]).get(n.pk)
    lat, lon = (place[0], place[1]) if place else (None, None)
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
                fov=fov_of(t["frames"], t["ds"]),
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


# ---- the sky survey behind the dome (spec 015 amendment, 2026-10-15) -------------------------------------------
# One all-sky image per survey, fetched once from the CDS image service and kept: right ascension runs from 360° at
# the left edge to 0° at the right (centred on 180°), declination from +90° at the top to −90° at the bottom.
SURVEYS = {
    "dss": ("CDS/P/DSS2/color", "DSS2 colour: STScI/NASA, coloured and HEALPix-ed by CDS"),
    "mellinger": ("CDS/P/Mellinger/color", "Mellinger all-sky colour mosaic (A. Mellinger), via CDS"),
}
SURVEY_SIZE = (4096, 2048)


def survey_file(name: str) -> Path:
    """The cached all-sky image, fetched the first time it's asked for."""
    import urllib.parse
    import urllib.request

    from django.conf import settings

    hips, _ = SURVEYS[name]
    folder = Path(settings.STATION_ROOT) / "cache" / "sky"
    path = folder / f"{name}-{SURVEY_SIZE[0]}.jpg"
    if path.exists() and path.stat().st_size > 10_000:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode(
        {
            "hips": hips,
            "width": SURVEY_SIZE[0],
            "height": SURVEY_SIZE[1],
            "projection": "CAR",
            "ra": 180,
            "dec": 0,
            "fov": 360,
            "format": "jpg",
            "coordsys": "icrs",
        }
    )
    url = f"https://alasky.cds.unistra.fr/hips-image-services/hips2fits?{query}"
    part = path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=180) as resp, part.open("wb") as out:  # noqa: S310 (a fixed https host)
        out.write(resp.read())
    part.replace(path)
    return path


@router.get("/sky/survey/{name}", response={200: None, 404: None, 502: None})
def sky_survey(request, name: str):
    """The all-sky survey image the dome draws behind its tracks; `name` is dss or mellinger."""
    from django.http import FileResponse, HttpResponse

    if name not in SURVEYS:
        return HttpResponse(status=404)
    try:
        path = survey_file(name)
    except OSError as exc:
        log.warning("Sky survey %s couldn't be fetched: %s", name, exc)
        return HttpResponse(status=502)
    resp = FileResponse(path.open("rb"), content_type="image/jpeg")
    resp["Cache-Control"] = "private, max-age=2592000"
    resp["X-Credit"] = SURVEYS[name][1]
    return resp
