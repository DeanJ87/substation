"""Plate solving (spec 009, owner decision 2026-10-10): Siril's own solver against its local star catalogues, so
it works offline. The result says where a light really points: centre, rotation, scale and field."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from django.conf import settings

from apps.catalogue.models import Frame, FrameStatus, FrameType
from substation.tasks import PRIORITY_BULK, station_task

from .models import MeasureState, PlateSolve, SolveState, SubMeasurement

log = logging.getLogger("substation.processing")

CATALOGUES = ("namedstars.dat", "unnamedstars.dat", "deepstars.dat", "USNO-NOMAD-1e8.dat")


def catalogue_dir() -> Path:
    return Path(getattr(settings, "SIRIL_CATALOGUE_DIR", Path.home() / ".local/share/kstars"))


def available() -> bool:
    """Solving is on only when every local catalogue is installed (Siril then never goes online)."""
    d = catalogue_dir()
    return all((d / n).is_file() for n in CATALOGUES)


def _dms(text: str) -> float | None:
    """'02h32m39.1s' or '+61°32\\'21.5"' or '02d 44m 18.30s' → decimal (hours stay hours)."""
    m = re.match(r"\s*([+-]?)(\d+)\D+(\d+)\D+([\d.]+)", text)
    if not m:
        try:
            return float(text)
        except ValueError:
            return None
    sign = -1 if m.group(1) == "-" else 1
    return sign * (int(m.group(2)) + int(m.group(3)) / 60 + float(m.group(4)) / 3600)


def parse_solution(lines: list[str]) -> dict:
    """Pick the solution out of Siril's log: centre, resolution, rotation, field of view."""
    out: dict = {}
    for line in lines:
        low = line.lower()
        m = re.search(r"alpha:\s*([^,]+),\s*delta:\s*(.+)$", line, re.IGNORECASE)
        if m:
            ra_h, dec = _dms(m.group(1)), _dms(m.group(2))
            if ra_h is not None and dec is not None:
                out["ra_deg"], out["dec_deg"] = ra_h * 15, dec
        m = re.search(r"resolution:\s*([\d.]+)\s*arcsec", low)
        if m:
            out["scale_arcsec"] = float(m.group(1))
        m = re.search(r"up is\s*([+-]?[\d.]+)\s*deg", low)
        if m:
            out["rotation_deg"] = float(m.group(1)) % 360
            out["flipped"] = "(flipped)" in low
        m = re.search(r"field of view:\s*(.+?)\s+x\s+(.+)$", line, re.IGNORECASE)
        if m:
            w, h = _span(m.group(1)), _span(m.group(2))
            if w is not None and h is not None:
                out["fov_w_deg"], out["fov_h_deg"] = w, h
    return out


def _span(text: str) -> float | None:
    """A field size in degrees. Siril prints "04d 04m 52.01s" for wide fields but "26m 55.59s" under a degree;
    reading the second as d-m-s made a 0.45° field 26.9° (Horsehead, found 2026-10-12)."""
    parts: dict[str, float] = dict((u, float(n)) for n, u in re.findall(r"([\d.]+)\s*([dhms°'\"])", text))
    if not parts:
        return _dms(text)
    deg = parts.get("d", parts.get("°", 0.0))
    mins = parts.get("m", parts.get("'", 0.0))
    secs = parts.get("s", parts.get('"', 0.0))
    return deg + mins / 60 + secs / 3600


FEW_STARS = 300  # below this many detected stars a failed solve is put down to the sky, not the solver


def _reason(lines: list[str], stars: int | None = None) -> str:
    text = " ".join(lines).lower()
    if stars is not None and stars < FEW_STARS and "cannot download" not in text:
        return f"Only {stars} stars, too few to solve."
    if "not enough stars" in text or "few stars" in text:
        return "Too few stars to solve."
    if "could not be aligned" in text:
        return "No catalogue match near the header position. Check pointing and focal length."
    if "cannot download" in text:
        return "Star catalogues not installed."
    return "Siril couldn't solve it."


@station_task(queue_name="process", priority=PRIORITY_BULK - 20, max_attempts=1)
def solve_light(sha256: str) -> dict:
    """Solve one light, from its calibrated file when cached, else the capture."""
    from apps.engine.siril import engine

    from .tasks import source_path

    if not available():
        return {"result": "no catalogues"}
    f = Frame.objects.get(pk=sha256)
    m = SubMeasurement.objects.filter(frame=f).first()
    cal = Path(m.calibrated_path) if m and m.calibrated_path else None
    from_cal = bool(cal and cal.exists())
    src = cal if from_cal else source_path(f)
    if src is None:
        return {"result": "no file"}
    # library paths often have spaces ("M31 - Andromeda Galaxy"): Siril takes the path quoted. (Not a symlink in a
    # scratch folder: on Docker Desktop's bind mounts those fail now and then with "no such file".)
    eng = engine()
    eng.run(f'load "{src}"')
    t = time.monotonic()
    r = eng.run("platesolve -force -downscale", timeout=180, check=False)
    secs = round(time.monotonic() - t, 1)
    sol = parse_solution(r.log)
    if r.ok and "ra_deg" in sol:
        PlateSolve.objects.update_or_create(
            frame=f,
            defaults={
                "state": SolveState.SOLVED,
                "seconds": secs,
                "reason": "",
                "source": "calibrated" if from_cal else "raw",
                # kept whole, so a mosaic writes it into its copy of the sub instead of solving it again (004-DR-26)
                "wcs": _saved_wcs(eng, f.pk) if from_cal else {},
                **sol,
            },
        )
        return {"result": "solved", **sol}
    PlateSolve.objects.update_or_create(
        frame=f,
        defaults={
            "state": SolveState.FAILED,
            "seconds": secs,
            "reason": _reason(r.log, m.stars if m else None),
        },
    )
    return {"result": "failed"}


@station_task(queue_name="process", priority=PRIORITY_BULK - 30, max_attempts=1)
def backfill_solves(limit: int = 5000) -> dict:
    """Queue solves for measured lights that have none yet (009 P9): low priority, labelled in Activity."""
    from substation.tasks import enqueue

    if not available():
        return {"queued": 0, "result": "no catalogues"}
    shas = list(
        Frame.objects.filter(
            frame_type=FrameType.LIGHT,
            status=FrameStatus.CATALOGUED,
            measurement__state=MeasureState.DONE,
            solve__isnull=True,
        ).values_list("pk", flat=True)[:limit]
    )
    for sha in shas:
        enqueue(solve_light, sha, dedupe_key=f"solve:{sha}")
    return {"queued": len(shas)}


def framing(dataset) -> dict | None:  # noqa: ANN001
    """A dataset's framing from its solves (009 P10): median centre, field and scale, the mean rotation (on the
    circle, so 359° and 1° average to 0°), and the sub that shows it best (most stars) with its mirroring."""
    import math
    import statistics

    rows = list(
        PlateSolve.objects.filter(frame__dataset=dataset, state=SolveState.SOLVED).values_list(
            "ra_deg", "dec_deg", "rotation_deg", "fov_w_deg", "fov_h_deg", "scale_arcsec"
        )[:200]
    )
    rows = [r for r in rows if None not in r]
    if not rows:
        return None
    med = [statistics.median(float(r[i] or 0) for r in rows) for i in (0, 1, 3, 4, 5)]
    best = (
        PlateSolve.objects.filter(frame__dataset=dataset, state=SolveState.SOLVED)
        .exclude(frame__measurement__preview_path="")
        .select_related("frame__measurement")
        .order_by("-frame__measurement__stars")
        .first()
    )
    flips = list(
        PlateSolve.objects.filter(frame__dataset=dataset, state=SolveState.SOLVED)
        .exclude(flipped=None)
        .values_list("flipped", flat=True)[:200]
    )
    # mirroring belongs to the camera and optics, so it holds for the whole dataset; a meridian flip only turns
    # the field 180°, which leaves its outline unchanged: average the outline's angle on the doubled circle
    mirrored = (sum(1 for x in flips if x) * 2 > len(flips)) if flips else False
    angles = [math.radians(-float(r[2] or 0) if mirrored else float(r[2] or 0)) for r in rows]
    sx, cx = sum(math.sin(2 * a) for a in angles), sum(math.cos(2 * a) for a in angles)
    outline = math.degrees(math.atan2(sx, cx)) / 2 % 180
    from .models import Master, MasterState

    master = (
        Master.objects.filter(dataset=dataset, state__in=[MasterState.CURRENT, MasterState.STALE])
        .exclude(preview_path="")
        .exclude(solve={})
        .order_by("-finished_at")
        .first()
    )
    if master is not None and "ra_deg" not in master.solve:
        master = None
    return {
        "master": master,
        "ra": med[0],
        "dec": med[1],
        "rotation": outline,
        "fov_w": med[2],
        "fov_h": med[3],
        "scale": med[4],
        "solved": len(rows),
        "flipped": False,  # outline: unmirrored form
        "mirrored": mirrored if flips else None,
        "image": best.frame_id if best else None,
        "image_rotation": best.rotation_deg if best else None,
        "image_flipped": best.flipped if best else None,
        "image_source": best.source if best else "",
    }


def top_down(frame) -> bool:  # noqa: ANN001
    snap = frame.headers.first()
    v = ((snap.keywords or {}).get("ROWORDER") or {}) if snap else {}
    return str(v.get("value") if isinstance(v, dict) else v).upper() == "TOP-DOWN"


def master_corners(m, frame=None, ref: dict | None = None) -> list[tuple[float, float]]:  # noqa: ANN001
    """Where a master's preview sits: from the master's own solve, flipped only when the master file itself stores
    its top row first. (It used to follow the dataset's first sub; a dataset mixing NINA top-down FITS with XISF
    put M81 Hα's labels upside down — M82 named in empty sky, 2026-10-12.) `frame` is kept for callers."""
    from pathlib import Path

    from astropy.io import fits

    sol = m.solve
    one = {
        "ra": sol["ra_deg"],
        "dec": sol["dec_deg"],
        "rotation": sol["rotation_deg"],
        "fov_w": sol["fov_w_deg"],
        "fov_h": sol["fov_h_deg"],
        "flipped": bool(sol.get("flipped")),
    }
    tl, tr, br, bl = corners(one, ref or {"ra": one["ra"], "dec": one["dec"]})
    path = Path(m.output_path or "")
    td = path.is_file() and str(fits.getheader(path).get("ROWORDER", "")).strip().upper() == "TOP-DOWN"
    if td:
        return [bl, br, tr, tl]
    return [tl, tr, br, bl]


def image_corners(ps: PlateSolve, ref: dict) -> list[tuple[float, float]]:
    """Where a sub's preview sits on the sky. The preview of a top-down capture (a DSLR's FITS) is drawn the way the
    capture reads, but Siril solves its calibrated copy upside down (mirrored, rotation 180° − θ), so a solve of the
    calibrated copy puts the preview's top at the bottom: swap them (checked 2026-10-10, Heart Nebula A7 III)."""
    one = {
        "ra": ps.ra_deg,
        "dec": ps.dec_deg,
        "rotation": ps.rotation_deg,
        "fov_w": ps.fov_w_deg,
        "fov_h": ps.fov_h_deg,
        "flipped": bool(ps.flipped),
    }
    tl, tr, br, bl = corners(one, ref)
    if ps.source == "calibrated" and top_down(ps.frame):
        return [bl, br, tr, tl]
    return [tl, tr, br, bl]


def _tangent(f: dict, ref: dict) -> tuple[float, float]:
    """A centre in degrees east and north of the reference centre (small-field approximation)."""
    import math

    dra = ((f["ra"] - ref["ra"] + 180) % 360) - 180
    return dra * math.cos(math.radians(ref["dec"])), f["dec"] - ref["dec"]


def corners(
    f: dict, ref: dict, rotation: float | None = None, flipped: bool | None = None
) -> list[tuple[float, float]]:
    """The image's corners as displayed (top-left, top-right, bottom-right, bottom-left) in degrees east and north
    of the reference centre. Siril reports the angle of the image's up direction counter-clockwise from north,
    and whether the image is mirrored; previews are drawn the way Siril shows the image, so these corners place
    a preview exactly on the sky."""
    import math

    cx, cy = _tangent(f, ref)
    t = math.radians(f["rotation"] if rotation is None else rotation)
    # (east, north) unit vectors of the displayed image's up and right edges, checked against the WCS Siril
    # writes (2026-10-10, unmirrored and mirrored solves): for a mirrored image the angle runs the other way
    if f.get("flipped") if flipped is None else flipped:
        up, right = (-math.sin(t), math.cos(t)), (math.cos(t), math.sin(t))
    else:
        up, right = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
    w, h = f["fov_w"] / 2, f["fov_h"] / 2
    return [
        (cx + sx * w * right[0] + sy * h * up[0], cy + sx * w * right[1] + sy * h * up[1])
        for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))
    ]


def _inside(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    sign = 0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        c = (x2 - x1) * (pt[1] - y1) - (y2 - y1) * (pt[0] - x1)
        if c != 0:
            if sign and (c > 0) != (sign > 0):
                return False
            sign = 1 if c > 0 else -1
    return True


def overlap(f: dict, ref: dict, n: int = 40) -> float:
    """Share of the reference field this framing covers (0–1), by sampling the reference field on a grid."""
    if f is ref:
        return 1.0
    mine = corners(f, ref)
    tl, tr, _br, bl = corners(ref, ref)
    inside = 0
    for i in range(n):
        for j in range(n):
            u, v = (i + 0.5) / n, (j + 0.5) / n
            pt = (
                tl[0] + u * (tr[0] - tl[0]) + v * (bl[0] - tl[0]),
                tl[1] + u * (tr[1] - tl[1]) + v * (bl[1] - tl[1]),
            )
            inside += _inside(pt, mine)
    return inside / (n * n)


@station_task(queue_name="process", priority=PRIORITY_BULK, max_attempts=1)
def solve_master(master_id: int) -> dict:
    """Plate-solve a finished master (009, owner 2026-10-10) so Framing can show it, deeper than any single sub."""
    from apps.engine.siril import engine

    from .models import Master

    m = Master.objects.filter(pk=master_id).first()
    if m is None or not m.output_path or not Path(m.output_path).exists() or not available():
        return {"result": "nothing to solve"}
    # start from where the dataset's subs solved, not the header: a master keeps its reference sub's mount pointing,
    # which can be a degree off, and a solve that starts there can lock onto the wrong field (Heart panel 1 came
    # out on panel 2's position, 2026-10-10)
    guide = framing(m.dataset)
    eng = engine()
    eng.run(f'load "{m.output_path}"')
    start = f"{guide['ra']:.5f},{guide['dec']:.5f} " if guide else ""
    # SIP distortion terms, kept with the solve: labels near the edges land on their objects, not a few
    # arcminutes off as the centre-rotation-scale summary put them (NGC 3077 on M81, 2026-10-13)
    r = eng.run(f"platesolve {start}-force -downscale -order=3", timeout=300, check=False)
    sol = parse_solution(r.log)
    ok = r.ok and "ra_deg" in sol
    if ok:
        sol["wcs"] = _saved_wcs(eng, m.pk)
    if ok and guide:
        import math

        dra = (((sol["ra_deg"] - guide["ra"] + 180) % 360) - 180) * math.cos(math.radians(guide["dec"]))
        if math.hypot(dra, sol["dec_deg"] - guide["dec"]) > 0.5:
            ok = False  # not where its own subs are: a false match
    Master.objects.filter(pk=m.pk).update(solve=sol if ok else {"failed": True})
    return {"result": "solved" if ok else "failed"}


WCS_KEYS = re.compile(
    r"^(CTYPE|CRVAL|CRPIX|CDELT|CUNIT|CD\d_\d|PC\d_\d|A_|B_|AP_|BP_|LONPOLE|LATPOLE|RADESYS|EQUINOX|NAXIS\d|ROWORDER)"
)


def _saved_wcs(eng, pk: int | str) -> dict:  # noqa: ANN001
    """The solved image's WCS keywords (with SIP), from a throwaway save of the image Siril just solved."""
    import tempfile

    from astropy.io import fits

    tmp = Path(tempfile.mkdtemp(prefix="wcs-", dir=str(settings.WORK_DIR)))
    try:
        eng.run(f'save "{tmp}/wcs_{pk}"', check=False)
        f = next(tmp.glob(f"wcs_{pk}.*"), None)
        if f is None:
            return {}
        h = fits.getheader(f)
        return {k: h[k] for k in h if WCS_KEYS.match(k) and not isinstance(h[k], bool | type(None))}
    except Exception:  # noqa: BLE001 — the summary solve still works without it
        return {}
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


@station_task(queue_name="process", priority=PRIORITY_BULK - 5, max_attempts=1)
def backfill_master_solves() -> dict:
    from substation.tasks import enqueue

    from .models import Master, MasterState

    n = 0
    for pk in (
        Master.objects.filter(state__in=[MasterState.CURRENT, MasterState.STALE], solve={})
        .exclude(output_path="")
        .values_list("pk", flat=True)
    ):
        enqueue(solve_master, pk, dedupe_key=f"solve-master:{pk}")
        n += 1
    return {"queued": n}
