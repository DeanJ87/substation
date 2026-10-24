"""Cumulative progressive stacks of a finished project (020-DR-15).

A stack after each night: night 1, then nights 1–2, 1–3 … up to all of them; more than MAX_CHECKPOINTS nights are
grouped into contiguous, near-equal groups. Every channel's subs are registered once, onto one pinned reference,
so every checkpoint has the same framing; each checkpoint stacks its own prefix of the subs with the stacking
options of a master build. The images share one crop, are level-matched to the full stack and drawn with the full
stack's stretch, so the signal stays put and the noise is seen to fall. They live in SubStation's cache
(STATION_ROOT/cache/progression), never in Completed (020-DR-12)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import statistics
import time
import warnings
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from django.conf import settings
from django.utils import timezone

from apps.catalogue.models import Frame
from substation.tasks import (
    PRIORITY_BULK,
    Cancelled,
    Interrupted,
    Reschedule,
    check_cancelled,
    check_interrupted,
    enqueue,
    report_progress,
    station_task,
)

from .models import FinishedProject, Progression, ProgressionState

log = logging.getLogger("substation.progression")

ALGO_V = 1  # bump when the images would come out differently from the same subs
MAX_CHECKPOINTS = 12
WIDTH = 2400  # inputs are binned to about this width, and images fit inside it
JPEG_QUALITY = 88
RECAL_AUTO_LIMIT = 0.3  # an automatic start waits for the button when more of the subs need calibrating again
SINGLE_FIELD = "Progression is for single-field projects for now."
MAPPINGS = ("HOO", "SHO", "RGB", "OSC", "MONO")

Kept = dict[str, list[tuple[Frame, float]]]  # filter → (sub, weight), capture order


# -- what would be built --------------------------------------------------------------------------------------


def kept_subs(proj: FinishedProject) -> Kept:
    """The subs a default master build would use (included and measured), per filter, in capture order."""
    from apps.processing.masters import choose

    from .render import _datasets

    out: dict[str, dict[str, tuple[Frame, float]]] = defaultdict(dict)
    for ds in _datasets(proj):
        for f, included, weight, _why in choose(ds, None, "default"):
            if included:
                out[ds.filter_norm or ""][f.pk] = (f, weight)
    epoch = datetime.min.replace(tzinfo=UTC)
    return {
        k: sorted(v.values(), key=lambda fw: (fw[0].date_obs_utc or epoch, fw[0].pk)) for k, v in out.items()
    }


def _scale(frames: list[Frame]) -> float | None:
    from apps.processing.models import PlateSolve

    xs = [
        s
        for s in PlateSolve.objects.filter(frame__in=frames, state="solved").values_list(
            "scale_arcsec", flat=True
        )
        if s
    ]
    return statistics.median(xs) if xs else None


def availability(proj: FinishedProject, subs: Kept | None = None) -> str:
    """Why a progression can't be built for this project, or '' when it can."""
    from apps.processing.masters import mosaic_reason

    from .render import _is_mosaic

    if not proj.linked_projects.exists():
        return "Link this project to a SubStation project first."
    if _is_mosaic(proj):
        return f"This is a mosaic. {SINGLE_FIELD}"
    subs = kept_subs(proj) if subs is None else subs
    frames = [f for fs in subs.values() for f, _w in fs]
    if len(frames) < 2:
        return "Needs at least two kept subs."
    panels = {f.panel for f in frames if f.panel is not None}
    if len(panels) > 1:
        return f"Its subs come from {len(panels)} panels. {SINGLE_FIELD}"
    by_ds: dict[int, list[Frame]] = defaultdict(list)
    for f in frames:
        by_ds[f.dataset_id or 0].append(f)
    scales = [(len(fs), sc) for fs in by_ds.values() if (sc := _scale(fs))]
    if scales:
        ref = max(scales)[1]
        if any(abs(sc / ref - 1) > 0.10 for _n, sc in scales):
            return f"Its subs have more than one pixel scale. {SINGLE_FIELD}"
    why = mosaic_reason(frames)
    if why:
        return f"{why}. {SINGLE_FIELD}"
    if not default_mapping(subs, _colour_filters(subs))[1]:
        return "Needs at least two kept subs of one filter."
    return ""


def _is_colour(f: Frame) -> bool:
    from apps.processing.tasks import is_colour_frame

    try:
        return is_colour_frame(f)
    except Exception:  # noqa: BLE001 (no header snapshot: treat as mono)
        return False


def _colour_filters(subs: Kept) -> set[str]:
    return {k for k, fs in subs.items() if fs and _is_colour(fs[0][0])}


def default_mapping(subs: Kept, colour: set[str]) -> tuple[str, list[str]]:
    """The palette and the filters it stacks: Hα+OIII+SII → SHO, Hα+OIII → HOO, R+G+B → RGB (L is ignored),
    colour subs → OSC, else the filter with the most integration in grey (MONO). Only filters with two or more
    kept subs count."""

    def integration(k: str) -> float:
        return sum(f.exptime_s or 0 for f, _w in subs[k])

    usable = {k for k, fs in subs.items() if len(fs) >= 2}
    mono = usable - colour
    if {"Hα", "OIII", "SII"} <= mono:
        return "SHO", ["Hα", "OIII", "SII"]
    if {"Hα", "OIII"} <= mono:
        return "HOO", ["Hα", "OIII"]
    if {"R", "G", "B"} <= mono:
        return "RGB", ["R", "G", "B"]
    if usable & colour:
        return "OSC", [max(usable & colour, key=integration)]
    if mono:
        return "MONO", [max(mono, key=integration)]
    return "", []


def rgb_of(mapping: str, channels: list[str]) -> tuple[str, str, str] | None:
    """Which plane goes to red, green and blue (planes are named by filter; OSC's are r, g and b)."""
    from apps.processing.tasks import PALETTES

    if mapping in ("HOO", "SHO"):
        p = PALETTES[mapping.lower()]
        return p["r"], p["g"], p["b"]
    if mapping == "RGB":
        return "R", "G", "B"
    if mapping == "OSC":
        return "r", "g", "b"
    return None


def night_of(f: Frame) -> date:
    if f.night_id and f.night is not None:
        return f.night.date
    if f.date_obs_utc is not None:
        return (f.date_obs_utc - timedelta(hours=12)).date()
    return date(1970, 1, 1)


def group_nights(nights: list[date], max_n: int = MAX_CHECKPOINTS) -> list[list[date]]:
    """Nights in order, in at most `max_n` contiguous groups whose sizes differ by one at most."""
    n = len(nights)
    if n <= max_n:
        return [[d] for d in nights]
    bounds = [(i * n + max_n // 2) // max_n for i in range(max_n + 1)]
    return [nights[bounds[i] : bounds[i + 1]] for i in range(max_n)]


def _day(d: date, year: bool = False) -> str:
    return f"{d.day} {d:%b}" + (f" {d.year}" if year else "")


def label(nights: list[date]) -> str:
    """ "2 Sep", "3–9 Oct", "28 Sep–2 Oct", "28 Dec 2025–3 Jan 2026"."""
    a, b = nights[0], nights[-1]
    if a == b:
        return _day(a)
    if a.year != b.year:
        return f"{_day(a, True)}–{_day(b, True)}"
    if a.month != b.month:
        return f"{_day(a)}–{_day(b)}"
    return f"{a.day}–{_day(b)}"


def _reference(subs: Kept, mapping: str, channels: list[str], kept_ref: str = "") -> str:
    """The pinned registration reference: the one kept from an earlier run while its sub is still kept, else the
    sub with the most stars in Hα (or the only channel of OSC and MONO; any channel for RGB)."""
    pool = [f for c in channels for f, _w in subs[c]]
    if kept_ref and any(f.pk == kept_ref for f in pool):
        return kept_ref
    if "Hα" in channels:
        pool = [f for f, _w in subs["Hα"]]

    def stars(f: Frame) -> int:
        try:
            return f.measurement.stars or 0
        except Exception:  # noqa: BLE001
            return 0

    return max(pool, key=lambda f: (stars(f), f.pk)).pk if pool else ""


def _stacking() -> dict:
    from apps.processing.config import processing_settings

    cfg = processing_settings()["stacking"]
    return {k: cfg.get(k) for k in ("rejection", "sigma", "weighting")}


def ck_hash(input_hash: str, order: int, counts: dict[str, int]) -> str:
    return hashlib.sha256(json.dumps([input_hash, order, counts], sort_keys=True).encode()).hexdigest()


def plan(proj: FinishedProject, subs: Kept | None = None, kept_ref: str | None = None) -> dict[str, Any]:
    """What a build would make: the palette, its filters, the reference, the inputs per channel, the input hash and
    the checkpoints. Early nights are folded into the first checkpoint until every channel has two subs."""
    subs = kept_subs(proj) if subs is None else subs
    mapping, channels = default_mapping(subs, _colour_filters(subs))
    if not channels:
        return {
            "mapping": "",
            "channels": [],
            "subs": {},
            "reference": "",
            "input_hash": "",
            "checkpoints": [],
        }
    if kept_ref is None:
        kept_ref = Progression.objects.filter(project=proj).values_list("reference_frame", flat=True).first()
    ref = _reference(subs, mapping, channels, kept_ref or "")
    chosen = {c: subs[c] for c in channels}
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "v": ALGO_V,
                "mapping": mapping,
                "channels": channels,
                "reference": ref,
                "subs": {c: [[f.pk, round(w, 3)] for f, w in fs] for c, fs in chosen.items()},
                "stacking": _stacking(),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    nights = sorted({night_of(f) for fs in chosen.values() for f, _w in fs})
    first = 1
    while first < len(nights) and any(
        sum(1 for f, _w in fs if night_of(f) <= nights[first - 1]) < 2 for fs in chosen.values()
    ):
        first += 1
    groups = [nights[:first]] + (group_nights(nights[first:], MAX_CHECKPOINTS - 1) if nights[first:] else [])
    checkpoints = []
    for order, group in enumerate(groups, start=1):
        upto = group[-1]
        per = {c: [f for f, _w in fs if night_of(f) <= upto] for c, fs in chosen.items()}
        counts = {c: len(fs) for c, fs in per.items()}
        h = ck_hash(input_hash, order, counts)
        checkpoints.append(
            {
                "order": order,
                "nights": [d.isoformat() for d in group],
                "label": label(group),
                "integration_s": round(sum(f.exptime_s or 0 for fs in per.values() for f in fs), 1),
                "subs": sum(counts.values()),
                "filters": {
                    c: {"subs": len(fs), "integration_s": round(sum(f.exptime_s or 0 for f in fs), 1)}
                    for c, fs in per.items()
                },
                "hash": h,
                "file": f"{h}.jpg",
            }
        )
    return {
        "mapping": mapping,
        "channels": channels,
        "subs": chosen,
        "reference": ref,
        "input_hash": input_hash,
        "checkpoints": checkpoints,
    }


def cache_dir(proj_pk: int) -> Path:
    return Path(settings.STATION_ROOT) / "cache" / "progression" / f"fp{proj_pk}"


def image_path(proj_pk: int, ck: dict) -> Path:
    return cache_dir(proj_pk) / f"{ck['hash']}.jpg"


def _all_cached(proj_pk: int, checkpoints: list[dict]) -> bool:
    return bool(checkpoints) and all(image_path(proj_pk, ck).is_file() for ck in checkpoints)


def _needs_recal(p: dict[str, Any]) -> tuple[int, int]:
    """(subs whose calibrated copy is gone from the cache, subs)."""
    frames = [f for fs in p["subs"].values() for f, _w in fs]
    gone = 0
    for f in frames:
        try:
            cal = f.measurement.calibrated_path
        except Exception:  # noqa: BLE001
            cal = ""
        if not cal or not Path(cal).exists():
            gone += 1
    return gone, len(frames)


def start(proj: FinishedProject, auto: bool = False, force: bool = False) -> Progression:
    """Queue a build, or say why not. An automatic start (after linking) waits for the button when more than
    RECAL_AUTO_LIMIT of the subs would need calibrating again; nothing is queued when every image is cached."""
    prog, _ = Progression.objects.get_or_create(project=proj)
    if prog.state in (ProgressionState.QUEUED, ProgressionState.RUNNING) and not force:
        return prog
    subs = kept_subs(proj)
    why = availability(proj, subs)
    if why:
        Progression.objects.filter(pk=prog.pk).update(
            state=ProgressionState.UNAVAILABLE, reason=why, step="", progress=0
        )
        prog.refresh_from_db()
        return prog
    p = plan(proj, subs, prog.reference_frame)
    if not force and p["input_hash"] == prog.input_hash and _all_cached(proj.pk, prog.checkpoints):
        if prog.state != ProgressionState.DONE:
            Progression.objects.filter(pk=prog.pk).update(state=ProgressionState.DONE, reason="")
            prog.refresh_from_db()
        return prog
    if auto and not _all_cached(proj.pk, p["checkpoints"]):
        gone, total = _needs_recal(p)
        if total and gone / total > RECAL_AUTO_LIMIT:
            Progression.objects.filter(pk=prog.pk).update(
                state=prog.state if prog.state == ProgressionState.DONE else ProgressionState.NONE,
                reason=(
                    f"{gone} of {total} subs would need calibrating again first, so it wasn't built "
                    "automatically. Generate it when you want it."
                ),
            )
            prog.refresh_from_db()
            return prog
    job = enqueue(
        build_progression, proj.pk, force, dedupe_key=f"progression:{proj.pk}", priority=PRIORITY_BULK
    )
    Progression.objects.filter(pk=prog.pk).update(
        state=ProgressionState.QUEUED, reason="", step="", progress=0, task_id=job.id
    )
    prog.refresh_from_db()
    return prog


def reconcile_progressions() -> int:
    """A progression whose queue job ended without it (a worker stopped, a job cancelled in Activity) takes the
    job's outcome, as masters do. Returns those changed."""
    from substation.tasks.models import Task, TaskStatus

    n = 0
    for p in Progression.objects.filter(
        state__in=[ProgressionState.QUEUED, ProgressionState.RUNNING]
    ).exclude(task=None):
        t = Task.objects.filter(pk=str(p.task_id)).values("status", "error").first()
        if t is None or t["status"] in (TaskStatus.READY, TaskStatus.RUNNING):
            continue
        if t["status"] == TaskStatus.CANCELLED:
            state, reason = ProgressionState.CANCELLED, "Cancelled in Activity."
        elif t["status"] == TaskStatus.SUCCEEDED:  # it ended early (gone, unavailable): nothing was built
            state, reason = ProgressionState.NONE, ""
        else:
            last = (t["error"] or "").strip().splitlines()[-1:] or ["The job stopped without finishing."]
            state, reason = ProgressionState.FAILED, last[0][:500]
        Progression.objects.filter(pk=p.pk).update(state=state, reason=reason, finished_at=timezone.now())
        n += 1
    return n


# -- the build --------------------------------------------------------------------------------------------------


def _step(prog: Progression, step: str, progress: float) -> None:
    Progression.objects.filter(pk=prog.pk).update(step=step[:200], progress=progress)
    report_progress(progress, f"Progressive stacks: {step}")


class _Live:
    """Siril's "progress: 42%" lines move the build between `lo` and `hi`."""

    def __init__(self, prog: Progression, step: str, lo: float, hi: float) -> None:
        self.prog, self.step, self.lo, self.hi = prog, step, lo, hi
        self.last = 0.0

    def __call__(self, line: str) -> None:
        from apps.processing.masters import _Live as MasterLive

        got = MasterLive.PCT.search(line)
        if not got:
            return
        frac = float(got.group(1)) / (100 if got.group(2) or float(got.group(1)) > 1 else 1)
        now = time.monotonic()
        if now - self.last < 3:
            return
        self.last = now
        _step(self.prog, self.step, self.lo + (self.hi - self.lo) * min(max(frac, 0.0), 1.0))


def bin_factor(width: int) -> int:
    return max(1, width // WIDTH)


def _bin_copy(src: Path, dest: Path, factor: int) -> None:
    """A float32 copy of a calibrated sub, block-averaged by `factor` (colour planes each), without its plate
    solution (which no longer fits)."""
    from astropy.io import fits

    from apps.processing.solving import WCS_KEYS

    with fits.open(src, memmap=False) as hl:
        data = np.asarray(hl[0].data, dtype=np.float32)
        header = hl[0].header.copy()
    if factor > 1:
        h, w = data.shape[-2:]
        h2, w2 = (h // factor) * factor, (w // factor) * factor
        data = data[..., :h2, :w2]
        data = data.reshape(*data.shape[:-2], h2 // factor, factor, w2 // factor, factor).mean(axis=(-3, -1))
    drop = [k for k in header if (WCS_KEYS.match(k) and k != "ROWORDER") or k.startswith(("BZERO", "BSCALE"))]
    for k in drop:
        del header[k]
    header["BITPIX"] = -32
    fits.PrimaryHDU(data=data.astype(np.float32), header=header).writeto(dest, overwrite=True)


def _sources(prog: Progression, frames: list[Frame], redo: Path) -> dict[str, Path]:
    """Each sub's calibrated file: the cached one (touched, so pruning doesn't take it mid-build), else calibrated
    again into `redo`. A sub that can't be is missing from the result."""
    from apps.processing.masters import recalibrate

    src: dict[str, Path] = {}
    pending: list[tuple[Frame, Path]] = []
    for f in frames:
        cal = Path(f.measurement.calibrated_path) if f.measurement.calibrated_path else None
        if cal is not None and cal.exists():
            with contextlib.suppress(OSError):
                os.utime(cal)
            src[f.pk] = cal
        else:
            pending.append((f, redo / f"{f.pk}.fit"))
    if pending:
        failed = recalibrate(pending, redo, lambda note, frac: _step(prog, note, 0.05 + 0.1 * frac))
        src.update({f.pk: out for f, out in pending if f.pk not in failed and out.exists()})
    return src


def _inputs(prog: Progression, p: dict[str, Any], work: Path) -> list[tuple[int, Frame]]:
    """Binned copies of every channel's kept subs, channel by channel in capture order, as work/sub_NNNNN.fit
    numbered 1, 2, 3 … with no gaps; (channel index, sub) for each number. Subs pruned from the calibrated cache
    are calibrated again first; one that can't be is left out."""
    from astropy.io import fits

    wanted = [(ci, f) for ci, c in enumerate(p["channels"]) for f, _w in p["subs"][c]]
    src = _sources(prog, [f for _ci, f in wanted], work / "recal")
    kept = [(ci, f) for ci, f in wanted if f.pk in src]
    if not kept:
        return []
    factor = bin_factor(int(fits.getheader(src[kept[0][1].pk]).get("NAXIS1") or 0))
    for i, (_ci, f) in enumerate(kept, start=1):
        _bin_copy(src[f.pk], work / f"sub_{i:05d}.fit", factor)
        if src[f.pk].is_relative_to(work):
            src[f.pk].unlink(missing_ok=True)  # a recalibrated full-size sub: only its binned copy is needed
        if i % 10 == 0:
            check_interrupted()
            _step(prog, f"Bin ({i} of {len(kept)})", 0.15 + 0.1 * i / len(kept))
    return kept


def _runs(positions: list[int]) -> list[tuple[int, int]]:
    """Sorted positions as contiguous (first, last) runs."""
    out: list[tuple[int, int]] = []
    for x in sorted(positions):
        if out and x == out[-1][1] + 1:
            out[-1] = (out[-1][0], x)
        else:
            out.append((x, x))
    return out


def _read(path: Path) -> np.ndarray:
    from astropy.io import fits

    with fits.open(path, memmap=False) as hl:
        data = np.array(hl[0].data, dtype=np.float32)
    if data.ndim == 3 and data.shape[0] == 1:
        data = data[0]
    return data


def _planes(data: np.ndarray, channel: str, colour: bool) -> dict[str, np.ndarray]:
    if colour and data.ndim == 3 and data.shape[0] == 3:
        return {"r": data[0], "g": data[1], "b": data[2]}
    return {channel: data if data.ndim == 2 else data.mean(axis=0)}


def _box(arrays: list[np.ndarray]) -> tuple[int, int, int, int]:
    """One crop for every checkpoint: the rectangle every stack covers."""
    from apps.processing.postprocess import edge_box

    h, w = arrays[0].shape[-2:]
    t, b, lft, r = 0, h, 0, w
    for a in arrays:
        bx = edge_box(a)
        if bx:
            t, b, lft, r = max(t, bx[0]), min(b, bx[1]), max(lft, bx[2]), min(r, bx[3])
    if b - t < 2 or r - lft < 2:
        return 0, h, 0, w
    return t, b, lft, r


def _blocks(a: np.ndarray, f: int) -> np.ndarray:
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    x = np.where(np.isfinite(a[:h, :w]) & (a[:h, :w] != 0), a[:h, :w], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an empty block is NaN, and skipped
        return np.nanmean(x.reshape(h // f, f, w // f, f), axis=(1, 3))


def level_match(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """x scaled and offset to y's levels, a·x + b by least squares. Fitted on block averages, where noise is small:
    fitted pixel by pixel, a noisier x pulls the slope down (regression dilution), which flattens its noise and
    hides exactly what a progression shows."""
    f = max(4, min(x.shape) // 100)
    xs, ys = _blocks(x, f).ravel(), _blocks(y, f).ravel()
    ok = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[ok].astype(np.float64), ys[ok].astype(np.float64)
    if xs.size < 10 or float(np.var(xs)) == 0:
        return x
    a, b = np.polyfit(xs, ys, 1)
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0:
        return x
    return (x * a + b).astype(np.float32)


def render_checkpoints(
    stacks: dict[int, dict[str, Path]], channels: list[str], mapping: str, colour: bool
) -> dict[int, Any]:
    """Each checkpoint as an 8-bit image (top row first), drawn as described in the module docstring; returns
    {order: PIL image} fitted inside WIDTH."""
    from PIL import Image

    from apps.processing.previews import compose_fixed, stretch_params

    orders = sorted(stacks)
    raw = {o: {c: _read(stacks[o][c]) for c in channels} for o in orders}
    t, b, lft, r = _box([a for o in orders for a in raw[o].values()])
    planes = {
        o: {k: v for c in channels for k, v in _planes(raw[o][c][..., t:b, lft:r], c, colour).items()}
        for o in orders
    }
    full = planes[orders[-1]]
    params = {k: stretch_params(np.nan_to_num(v)) for k, v in full.items()}
    rgb = rgb_of(mapping, channels)
    out = {}
    for o in orders:
        matched = {k: (v if o == orders[-1] else level_match(v, full[k])) for k, v in planes[o].items()}
        img = np.flipud(compose_fixed(matched, params, rgb))  # Siril writes FITS bottom-up
        pic = Image.fromarray(np.ascontiguousarray(img), mode="RGB" if img.ndim == 3 else "L")
        pic.thumbnail((WIDTH, WIDTH))
        out[o] = pic
    return out


def _save_jpeg(pic: Any, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        pic.save(tmp, "JPEG", quality=JPEG_QUALITY)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _prune(proj_pk: int, keep: set[str]) -> None:
    for f in cache_dir(proj_pk).glob("*.jpg"):
        if f.name not in keep:
            f.unlink(missing_ok=True)


def _done(prog: Progression, p: dict[str, Any], checkpoints: list[dict]) -> None:
    Progression.objects.filter(pk=prog.pk).update(
        state=ProgressionState.DONE,
        reason="",
        step="Done",
        progress=1.0,
        mapping=p["mapping"],
        reference_frame=p["reference"],
        input_hash=p["input_hash"],
        checkpoints=checkpoints,
        finished_at=timezone.now(),
    )
    _prune(prog.project_id, {ck["file"] for ck in checkpoints})


def _stack_all(
    eng: Any, prog: Progression, p: dict[str, Any], work: Path, kept: list[tuple[int, Frame]]
) -> dict[int, dict[str, Path]]:
    """Register once onto the pinned reference, then stack each checkpoint's prefix of each channel."""
    from apps.engine import parse
    from apps.processing.config import processing_settings
    from apps.processing.masters import _check_budget, _fit_registered, stack_options

    n = len(kept)
    eng.run(f"cd {work}")
    _step(prog, "Register", 0.25)
    _check_budget(work, n)
    ref = next((i for i, (_c, f) in enumerate(kept, start=1) if f.pk == p["reference"]), 1)
    _fit_registered(eng, work, n)
    eng.run(f"setref sub_ {ref}")
    eng.run("register sub_", timeout=7200, quiet=True, on_line=_Live(prog, "Register", 0.25, 0.5))
    eng.run("set32bits")
    seq = parse.seq_images(work / "r_sub_.seq")
    position = {im["filenum"]: k for k, im in enumerate(seq, start=1)}
    if len(position) < 2:
        raise RuntimeError("Fewer than two subs could be registered.")
    nights = {i: night_of(f) for i, (_c, f) in enumerate(kept, start=1)}
    cfg = processing_settings()["stacking"]
    out: dict[int, dict[str, Path]] = {}
    cks = p["checkpoints"]
    jobs = len(cks) * len(p["channels"])
    done = 0
    for ck in cks:
        upto = date.fromisoformat(ck["nights"][-1])
        files: dict[str, Path] = {}
        for ci, c in enumerate(p["channels"]):
            check_cancelled()
            check_interrupted()
            mine = [i for i, (cj, _f) in enumerate(kept, start=1) if cj == ci and nights[i] <= upto]
            at = [position[i] for i in mine if i in position]
            done += 1
            _step(prog, f"Stack {ck['label']} {c} ({done} of {jobs})", 0.5 + 0.4 * done / jobs)
            if not at:
                break
            if len(at) == 1:
                files[c] = work / f"r_sub_{seq[at[0] - 1]['filenum']:05d}.fit"
                continue
            eng.run(f"unselect r_sub_ 1 {len(seq)}", check=False)
            for a, b in _runs(at):
                eng.run(f"select r_sub_ {a} {b}", check=False)
            exposures = {round(kept[i - 1][1].exptime_s or 0, 3) for i in mine}
            # weighted by noise, whatever masters use: sharpness weighting gives the softest sub of a small stack
            # almost nothing, which hides the very noise drop a progression is there to show (real Siril, 2026-10-22)
            opts = stack_options({**cfg, "weighting": "snr"}, exposures, [], rejection=len(at) >= 3)
            name = f"ck{ck['order']:02d}_c{ci}"
            eng.run(
                f"stack r_sub_ {opts} -filter-incl -out={work / name} -32b".replace("  ", " "),
                timeout=7200,
                quiet=True,
            )
            files[c] = work / f"{name}.fit"
        if len(files) == len(p["channels"]):
            out[ck["order"]] = files
    if not out:
        raise RuntimeError("No checkpoint could be stacked.")
    return out


def _build(prog: Progression, p: dict[str, Any], work: Path) -> list[dict]:
    """Inputs, registration, stacks and images; returns the checkpoints made."""
    from apps.engine.siril import engine, heavy_memory

    _step(prog, "Select inputs", 0.02)
    kept = _inputs(prog, p, work)
    check_interrupted()
    if len(kept) < 2:
        raise RuntimeError("Fewer than two calibrated subs.")
    eng = engine()
    with heavy_memory():
        stacks = _stack_all(eng, prog, p, work, kept)
    _step(prog, "Draw", 0.9)
    pics = render_checkpoints(stacks, p["channels"], p["mapping"], p["mapping"] == "OSC")
    made = [ck for ck in p["checkpoints"] if ck["order"] in pics]
    for ck in made:
        _save_jpeg(pics[ck["order"]], image_path(prog.project_id, ck))
    return made


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def build_progression(fp_id: int, force: bool = False) -> dict:
    """Build a finished project's cumulative stacks (020-DR-15). Nothing runs when every image is cached."""
    proj = FinishedProject.objects.filter(pk=fp_id).first()
    if proj is None:
        return {"result": "gone"}
    prog, _ = Progression.objects.get_or_create(project=proj)
    if prog.state == ProgressionState.CANCELLED:
        return {"result": "cancelled"}
    from apps.processing.move_guard import wait_for_moves

    try:  # its subs may be moving (Archive, Bring back): it waits its turn (spec 013, 2026-10-24)
        wait_for_moves(proj.linked_projects.values_list("collection_id", flat=True))
    except Reschedule as r:
        Progression.objects.filter(pk=prog.pk).update(state=ProgressionState.QUEUED, reason=r.note)
        raise
    subs = kept_subs(proj)
    why = availability(proj, subs)
    if why:
        Progression.objects.filter(pk=prog.pk).update(state=ProgressionState.UNAVAILABLE, reason=why)
        return {"result": "unavailable"}
    p = plan(proj, subs, prog.reference_frame)
    if not force and _all_cached(proj.pk, p["checkpoints"]):
        _done(prog, p, p["checkpoints"])
        return {"result": "cached", "checkpoints": len(p["checkpoints"])}
    Progression.objects.filter(pk=prog.pk).update(
        state=ProgressionState.RUNNING, reason="", started_at=timezone.now(), progress=0
    )
    work = Path(settings.WORK_DIR) / "progression" / f"fp{proj.pk}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        made = _build(prog, p, work)
        _done(prog, p, made)
    except Interrupted:
        Progression.objects.filter(pk=prog.pk).update(
            state=ProgressionState.QUEUED, reason="Stopped by a restart; starts again."
        )
        raise
    except Reschedule as r:
        Progression.objects.filter(pk=prog.pk).update(state=ProgressionState.QUEUED, reason=r.note)
        raise
    except Cancelled:
        Progression.objects.filter(pk=prog.pk).update(
            state=ProgressionState.CANCELLED, reason="Cancelled.", finished_at=timezone.now()
        )
        raise
    except Exception as exc:
        Progression.objects.filter(pk=prog.pk).update(
            state=ProgressionState.FAILED, reason=str(exc)[:2000], finished_at=timezone.now()
        )
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"result": "done", "checkpoints": len(made)}
