"""Rigs, collections and suggestions (spec 006)."""

from __future__ import annotations

import math
import re
import statistics

from ..models import Collection, Dataset, Frame, FrameStatus, FrameType, Rig


def _kw(frame: Frame, key: str) -> float | None:
    for h in frame.headers.all():
        v = (h.keywords or {}).get(key, {}).get("value")
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


_SMART = re.compile(r"seestar|^s[35]0(\s*pro)?(_|\b)", re.IGNORECASE)


def is_smart_scope(telescope: str | None, camera: str | None) -> bool:
    """A Seestar calibrates in the camera: "ZWO Seestar S30 Pro", or TELESCOP "S30 Pro_db50a4a4" whatever
    INSTRUME says (some firmware writes the sensor, "imx585", or nothing)."""
    return any(_SMART.search((v or "").strip()) for v in (telescope, camera))


def smart_name(telescope: str | None, camera: str | None) -> str:
    text = f"{camera or ''} {telescope or ''}"
    m = re.search(r"s([35]0)(\s*pro)?", text, re.IGNORECASE)
    return f"Seestar S{m.group(1)}{' Pro' if m.group(2) else ''}" if m else "Seestar"


def _same_camera(ds: Dataset, rig: Rig) -> bool:
    from apps.processing.config import processing_settings

    eq = processing_settings().get("equipment", {})
    pair = eq.get("rig", {}).get(f"{ds.camera or ''}|{ds.telescope or ''}")
    cam = pair[0] if pair else eq.get("camera", {}).get(ds.camera or "", ds.camera)
    return not cam or not rig.camera or (cam or "") == rig.camera


def ensure_rig(ds: Dataset) -> Rig | None:
    """Detect the dataset's rig from a sample light's TELESCOP, INSTRUME and FOCALLEN (spec 006 FR-001). A rig whose
    camera isn't the dataset's (left by a rig merge that was later undone) is detected again."""
    if ds.rig_id and ds.rig is not None and _same_camera(ds, ds.rig):
        return ds.rig
    f = (
        Frame.objects.filter(dataset=ds, frame_type=FrameType.LIGHT)
        .prefetch_related("headers")
        .order_by("date_obs_utc")
        .first()
    )
    if f is None:
        return None
    focal = _kw(f, "FOCALLEN")
    key = f"{ds.telescope or ''}|{ds.camera or ''}|{focal or ''}"
    smart = is_smart_scope(ds.telescope, ds.camera)
    # the same camera and telescope with a focal length that differs by rounding (490.0 vs 489.92) is one rig
    same = Rig.objects.filter(camera=ds.camera or "", telescope=ds.telescope or "")
    near = Rig.objects.filter(key=key).first() or next(
        (r for r in same if focal and r.focal_mm and abs(r.focal_mm - focal) <= 0.02 * focal), None
    )
    rig, _ = (
        (near, False)
        if near is not None
        else Rig.objects.get_or_create(
            key=key,
            defaults={
                "name": smart_name(ds.telescope, ds.camera)
                if smart
                else ds.telescope or ds.camera or "Unknown rig",
                "telescope": ds.telescope or "",
                "camera": ds.camera or "",
                "focal_mm": focal,
                "pixel_um": _kw(f, "XPIXSZ"),
                "calibration": "none" if smart else "masters",
            },
        )
    )
    Dataset.objects.filter(pk=ds.pk).update(rig=rig)
    ds.rig = rig
    return rig


def label(ds: Dataset) -> str:
    """ "Askar 71F · Hα · Panel 3": rig, filter and framing (spec 006)."""
    rig = ds.rig.name if ds.rig_id and ds.rig else (ds.telescope or ds.camera or "Unknown rig")
    parts = [rig, ds.filter_norm]
    if ds.panel is not None:
        parts.append(f"Panel {ds.panel}")
    return " · ".join(p for p in parts if p)


def centre(ds: Dataset) -> tuple[float, float] | None:
    """Median pointing of the dataset (RA, Dec in degrees): plate solves where there are any (spec 009),
    else the header pointing of up to 15 lights."""
    from apps.processing.models import PlateSolve

    solved = [
        (r, d)
        for r, d in PlateSolve.objects.filter(frame__dataset=ds, state="solved").values_list(
            "ra_deg", "dec_deg"
        )[:50]
        if r is not None and d is not None
    ]
    if solved:
        return statistics.median(r for r, _ in solved), statistics.median(d for _, d in solved)
    ras, decs = [], []
    for f in Frame.objects.filter(dataset=ds, frame_type=FrameType.LIGHT).prefetch_related("headers")[:15]:
        ra, dec = _kw(f, "RA"), _kw(f, "DEC")
        if ra is not None and dec is not None:
            ras.append(ra)
            decs.append(dec)
    if not ras:
        return None
    return statistics.median(ras), statistics.median(decs)


def separation(a: tuple[float, float], b: tuple[float, float]) -> float:
    ra1, d1, ra2, d2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def suggest(ds: Dataset, centres: dict[int, tuple[float, float] | None] | None = None) -> dict:
    """{collection_id|None, name, why}: by object name first, then header pointing within 2°."""
    target = (ds.target or "").casefold()
    for col in Collection.objects.prefetch_related("datasets"):
        if any((d.target or "").casefold() == target for d in col.datasets.all()):
            return {"collection_id": col.pk, "name": col.name, "why": f"Same object name ({ds.target})."}
    mine = centre(ds)
    if mine is not None:
        best = None
        for col in Collection.objects.prefetch_related("datasets"):
            for d in col.datasets.all():
                c = (centres or {}).get(d.pk) if centres is not None and d.pk in centres else centre(d)
                if c is None:
                    continue
                sep = separation(mine, c)
                if sep <= 2 and (best is None or sep < best[0]):
                    best = (sep, col)
        if best is not None:
            sep, col = best
            return {
                "collection_id": col.pk,
                "name": col.name,
                "why": f"{sep * 60:.0f}′ from {col.name} (headers).",
            }
    return {"collection_id": None, "name": ds.target, "why": "No existing collection within 2°."}


def add_to_collection(ds_ids: list[int], collection: Collection) -> int:
    n = Dataset.objects.filter(pk__in=ds_ids).update(collection=collection)
    refresh_objects(collection)
    return n


def constellation_of(radec: tuple[float, float] | None) -> str:
    """The IAU constellation at a pointing ("Cassiopeia"), or "" when unknown."""
    if radec is None:
        return ""
    from astropy import units as u
    from astropy.coordinates import SkyCoord, get_constellation

    try:
        return str(get_constellation(SkyCoord(ra=radec[0] * u.deg, dec=radec[1] * u.deg)))
    except (ValueError, TypeError):
        return ""


SOLAR_SYSTEM = {"moon", "sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"}


def refresh_objects(col: Collection) -> None:
    targets = sorted({d.target for d in col.datasets.all() if d.target})
    col.objects_text = " · ".join(targets)
    # the Moon and planets move through the constellations, so none is named for them
    moving = bool(targets) and all(t.strip().casefold() in SOLAR_SYSTEM for t in targets)
    col.constellation = (
        ""
        if moving
        else next((c for c in (constellation_of(centre(d)) for d in col.datasets.all()[:5]) if c), "")
    )
    col.save(update_fields=["objects_text", "constellation"])


def lights_in(col_or_ds) -> object:  # noqa: ANN001
    return Frame.objects.filter(frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED)
