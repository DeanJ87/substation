"""Annotations (009 amendment 2026-10-12, owner): the named objects inside a solved
field, placed on its preview. The catalogues are Siril 1.4.2's own annotation lists (annotation_catalogues/, GPL-3.0,
from siril-common), so this works offline and needs no engine call: it is arithmetic on a solve that Siril made."""

from __future__ import annotations

import csv
import logging
import math
import re
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("substation.processing")

DATA = Path(__file__).parent / "annotation_catalogues"

# catalogue → kind shown in the UI; order matters: an object listed earlier wins over its aliases further down
CATALOGUES = (
    ("messier", "messier"),
    ("ngc", "ngc"),
    ("ic", "ic"),
    ("sh2", "sh2"),
    ("ldn", "ldn"),
    ("stars", "star"),
)


def _number(text: str) -> float | None:
    """The leading number of a field: a few rows carry a name after it ("8.8 Cetus A", Siril's M77)."""
    m = re.match(r"\s*(-?[\d.]+)", text or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def _alias_names(alias: str) -> set[str]:
    return {a.replace(" ", "").upper() for a in alias.split("/") if a.strip()}


@lru_cache(maxsize=1)
def catalogue() -> list[dict]:
    """Every object once: an NGC object that is also a Messier object (M1 = NGC1952) appears as the Messier one,
    carrying its other names."""
    out: list[dict] = []
    seen: set[str] = set()
    for name, kind in CATALOGUES:
        path = DATA / f"{name}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = row["name"].replace(" ", "").upper()
                if key in seen:
                    continue
                alias = (row.get("alias") or "").strip()
                seen.add(key)
                seen.update(_alias_names(alias))
                try:
                    ra, dec = float(row["ra"]), float(row["dec"])
                except (TypeError, ValueError):
                    continue
                out.append(
                    {
                        "name": row["name"],
                        "alias": alias,
                        "kind": kind,
                        "ra": ra,
                        "dec": dec,
                        "size_arcmin": _number(row.get("diameter") or ""),
                        "mag": _number(row.get("mag") or ""),
                    }
                )
    return out


def gnomonic(ra: float, dec: float, ra0: float, dec0: float) -> tuple[float, float] | None:
    """A sky position in degrees east and north of a field centre, on the tangent plane (None: behind it)."""
    a, d, a0, d0 = map(math.radians, (ra, dec, ra0, dec0))
    cos_c = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0)
    if cos_c <= 0:
        return None
    xi = math.cos(d) * math.sin(a - a0) / cos_c
    eta = (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0)) / cos_c
    return math.degrees(xi), math.degrees(eta)


def place(corners: list[tuple[float, float]], pt: tuple[float, float]) -> tuple[float, float]:
    """Where a tangent-plane point falls on the displayed image, as fractions of its width and height (0,0 is the
    top-left), from the image's corners (top-left, top-right, bottom-right, bottom-left)."""
    tl, tr, _br, bl = corners
    ax, ay = tr[0] - tl[0], tr[1] - tl[1]
    bx, by = bl[0] - tl[0], bl[1] - tl[1]
    px, py = pt[0] - tl[0], pt[1] - tl[1]
    det = ax * by - ay * bx
    return (px * by - py * bx) / det, (ax * py - ay * px) / det


def annotate(centre: tuple[float, float], fov_w: float, corners: list[tuple[float, float]]) -> list[dict]:
    """The catalogue objects inside a field, each with its position on the preview (u, v as fractions) and its
    size as a fraction of the image width. `corners` are the displayed image's corners in degrees east and north
    of `centre`."""
    ra0, dec0 = centre
    half = math.hypot(*[max(abs(c[i]) for c in corners) for i in (0, 1)])
    tl, tr, _br, bl = corners
    aspect = math.dist(tl, tr) / math.dist(
        tl, bl
    )  # width over height, to turn a width share into a height share
    out = []
    for obj in catalogue():
        # a cheap box test before the projection: most of the sky is nowhere near
        radius = (obj["size_arcmin"] or 0) / 120  # degrees
        reach = half + radius + 0.05
        if abs(obj["dec"] - dec0) > reach:
            continue
        p = gnomonic(obj["ra"], obj["dec"], ra0, dec0)
        if p is None or abs(p[0]) > reach or abs(p[1]) > reach:
            continue
        u, v = place(corners, p)
        size = obj["size_arcmin"] / 60 / fov_w if obj["size_arcmin"] and fov_w else None
        # in the field, or a large object whose outline reaches into it (NGC 7000 is wider than most fields that
        # show part of it): an object only partly in view is labelled at the edge it comes in from
        r_u, r_v = (size or 0) / 2, (size or 0) / 2 * aspect
        if not (-0.01 - r_u <= u <= 1.01 + r_u and -0.01 - r_v <= v <= 1.01 + r_v):
            continue
        out.append(
            {
                "name": obj["name"],
                "alias": obj["alias"],
                "kind": obj["kind"],
                "u": round(u, 5),
                "v": round(v, 5),
                "size": round(size, 5) if size else None,
                "mag": obj["mag"],
            }
        )
    # the biggest and brightest first, so a crowded field still labels what matters
    rank = {"messier": 0, "ngc": 1, "ic": 2, "sh2": 2, "star": 3, "ldn": 4}
    out.sort(key=lambda o: (rank[o["kind"]], -(o["size"] or 0), o["mag"] if o["mag"] is not None else 99))
    return out


def for_solve(ps) -> list[dict]:  # noqa: ANN001
    from .solving import image_corners

    if ps is None or ps.state != "solved" or None in (ps.ra_deg, ps.dec_deg, ps.rotation_deg, ps.fov_w_deg):
        return []
    ref = {"ra": ps.ra_deg, "dec": ps.dec_deg}
    return annotate((ps.ra_deg, ps.dec_deg), ps.fov_w_deg, image_corners(ps, ref))


def annotate_wcs(header: dict, top_down: bool) -> list[dict]:
    """Catalogue objects placed through the solve's full WCS (with SIP distortion): exact across the field."""
    import warnings

    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning

    h = fits.Header()
    for k, v in header.items():
        h[k] = v
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        w = WCS(h)
    W, H = int(h.get("NAXIS1") or 0), int(h.get("NAXIS2") or 0)
    if not W or not H:
        return []
    from astropy.wcs.utils import proj_plane_pixel_scales

    ra0, dec0 = (float(x) for x in w.wcs.crval)
    px = abs(float(proj_plane_pixel_scales(w)[0]))  # degrees per pixel
    fov_w = px * W
    reach = math.hypot(W, H) * px / 2 + 0.1
    cands = [o for o in catalogue() if abs(o["dec"] - dec0) < reach + (o["size_arcmin"] or 0) / 120]
    out: list[dict] = []
    if not cands:
        return out
    import numpy as np

    ras = np.array([o["ra"] for o in cands])
    decs = np.array([o["dec"] for o in cands])
    # the linear part first: SIP polynomials blow up far outside the frame (astropy then refuses the lot), so
    # only objects near it get the distortion-corrected position; any that still won't converge are dropped
    lx, ly = w.wcs_world2pix(ras, decs, 0)
    near = (
        np.isfinite(lx)
        & np.isfinite(ly)
        & (lx > -0.3 * W)
        & (lx < 1.3 * W)
        & (ly > -0.3 * H)
        & (ly < 1.3 * H)
    )
    cands = [o for o, k in zip(cands, near, strict=True) if k]
    if not cands:
        return out
    from astropy.wcs import NoConvergence

    try:
        xs, ys = w.all_world2pix(ras[near], decs[near], 0, quiet=True)
    except NoConvergence as exc:
        xs, ys = exc.best_solution[:, 0], exc.best_solution[:, 1]
    for o, x, y in zip(cands, xs, ys, strict=True):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        u = (x + 0.5) / W
        v = (y + 0.5) / H if top_down else 1 - (y + 0.5) / H  # previews show bottom-up FITS the right way up
        size = o["size_arcmin"] / 60 / fov_w if o["size_arcmin"] and fov_w else None
        r = (size or 0) / 2
        if not (-0.01 - r <= u <= 1.01 + r and -0.01 - r * W / H <= v <= 1.01 + r * W / H):
            continue
        out.append(
            {
                "name": o["name"],
                "alias": o["alias"],
                "kind": o["kind"],
                "u": round(float(u), 5),
                "v": round(float(v), 5),
                "size": round(size, 5) if size else None,
                "mag": o["mag"],
            }
        )
    rank = {"messier": 0, "ngc": 1, "ic": 2, "sh2": 2, "star": 3, "ldn": 4}
    out.sort(key=lambda o: (rank[o["kind"]], -(o["size"] or 0), o["mag"] if o["mag"] is not None else 99))
    return out


def for_master(m) -> list[dict]:  # noqa: ANN001
    from apps.catalogue.models import Frame

    from .solving import master_corners

    sol = m.solve or {}
    if "ra_deg" not in sol:
        return []
    if sol.get("wcs"):
        wcs = sol["wcs"]
        try:
            return annotate_wcs(wcs, str(wcs.get("ROWORDER", "")).strip().upper() == "TOP-DOWN")
        except Exception:  # noqa: BLE001 — labels from the summary solve rather than none
            log.warning(
                "Annotating master %s through its WCS failed; using the summary solve", m.pk, exc_info=True
            )
    some = Frame.objects.filter(dataset=m.dataset, frame_type="light").prefetch_related("headers").first()
    ref = {"ra": sol["ra_deg"], "dec": sol["dec_deg"]}
    return annotate((sol["ra_deg"], sol["dec_deg"]), sol["fov_w_deg"], master_corners(m, some, ref))
