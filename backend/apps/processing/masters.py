"""Integrations ("Master vN", spec 004 US1–US2; v2 design D5): choose subs by scope and rule, register and
stack them with Siril, keep the result with its recipe. The recipe is enough to re-run it."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Copy, Dataset, Frame, FrameStatus, FrameType
from substation.events.emit import emit
from substation.tasks import (
    PRIORITY_BULK,
    Cancelled,
    Interrupted,
    Reschedule,
    check_interrupted,
    enqueue,
    report_progress,
    station_task,
)

from .config import processing_settings
from .effective import effective
from .models import MachineGrade, Master, MasterMember, MasterState, MeasureState, SubMeasurement

log = logging.getLogger("substation.masters")

RULES = {
    "default": "Accepted and down-weighted subs",
    "accepted": "Accepted subs only",
    "graded": "Every graded sub",
    "everything": "Every sub, including rejected ones",
}
STEPS = ["Select inputs", "Calibrate", "Register", "Normalise", "Integrate", "Write"]

# 004-DR-35: a master's resolution. Drizzle ×2 registers the subs onto a grid twice as fine (Siril's HST drizzle,
# pixel fraction 1, square kernel); Bin 2×2 averages each 2×2 block of the calibrated subs before registration.
RESOLUTIONS = {"normal": "", "drizzle2": "Drizzle ×2", "bin2": "Bin 2×2"}
DRIZZLE = "-drizzle -scale=2 -pixfrac=1.0 -kernel=square"


def resolution_of(m: Master | None) -> str:
    r = ((getattr(m, "recipe", None) or {}).get("options") or {}).get("resolution") or "normal"
    return r if r in RESOLUTIONS else "normal"


def pixel_factor(res: str) -> float:
    """How much bigger a master pixel is than a sub pixel: ½ drizzled, 2 binned."""
    return {"drizzle2": 0.5, "bin2": 2.0}.get(res, 1.0)


def scaled_wcs(wcs: dict, f: int) -> dict:
    """A stored plate solution for the image binned `f`×`f`: the pixel grid is coarser by `f`, the sky the same.
    Distortion terms (SIP) are left out: they were fitted on the unbinned pixels."""
    out: dict = {}
    for k, v in wcs.items():
        if re.match(r"^(A|B|AP|BP)_", k):
            continue
        if k in ("NAXIS1", "NAXIS2"):
            out[k] = int(v) // f
        elif k in ("CRPIX1", "CRPIX2"):
            out[k] = (float(v) - 0.5) / f + 0.5
        elif re.match(r"^(CD\d_\d|CDELT\d)$", k):
            out[k] = float(v) * f
        elif k in ("CTYPE1", "CTYPE2") and isinstance(v, str):
            out[k] = v.replace("-SIP", "")
        else:
            out[k] = v
    return out


def bin2x2(path: Path) -> None:
    """Replace the stack's link to a calibrated sub by its 2×2 average (the cache is never written to): each output
    pixel is the mean of four, an odd last row or column is dropped, and the header says so (binning, pixel size
    and plate solution follow)."""
    import numpy as np
    from astropy.io import fits

    with fits.open(path.resolve(), memmap=False) as hl:
        data = np.asarray(hl[0].data)
        header = hl[0].header.copy()
    h, w = data.shape[-2] // 2 * 2, data.shape[-1] // 2 * 2
    a = data[..., :h, :w].astype(np.float32)
    binned = (a[..., 0::2, 0::2] + a[..., 1::2, 0::2] + a[..., 0::2, 1::2] + a[..., 1::2, 1::2]) / 4
    if np.issubdtype(data.dtype, np.integer):
        out = np.clip(np.rint(binned), 0, 65535).astype(np.uint16)
    else:
        out = binned.astype(np.float32)
    for k in ("XBINNING", "YBINNING"):
        header[k] = int(header.get(k, 1) or 1) * 2
    for k in ("XPIXSZ", "YPIXSZ"):
        if k in header:
            header[k] = float(header[k]) * 2
    wcs = {
        k: header[k] for k in list(header) if re.match(r"^(CRPIX\d|CD\d_\d|CDELT\d|CTYPE\d|(A|B|AP|BP)_)", k)
    }
    if "CRPIX1" in wcs:
        for k in wcs:
            del header[k]
        for k, v in scaled_wcs(wcs, 2).items():
            header[k] = v
    header.add_history("SubStation: binned 2x2 (average) before registration")
    tmp = path.with_suffix(".part.fit")
    fits.PrimaryHDU(data=out, header=header).writeto(tmp, overwrite=True)
    path.unlink(missing_ok=True)
    tmp.replace(path)


def _bin_inputs(m: Master, work: Path, ck: dict, order: dict) -> None:
    """Bin 2×2 every input before registration (004-DR-35); a resumed folder that did it already isn't binned twice."""
    if "binned" in ck["done"]:
        return
    n = len(order)
    for k, i in enumerate(sorted(order), start=1):
        bin2x2(work / f"sub_{i:05d}.fit")
        if k % 20 == 0 or k == n:
            _step(m, f"Bin 2×2 ({k} of {n})", 0.1 + 0.1 * k / n)
    ck["done"].append("binned")
    _save_checkpoint(work, ck)


def scope_of(recipe: dict) -> dict:
    """The scope a recipe (or a request) names beyond its nights (004 T008/T009): a date range, more datasets of the
    same target, filter, camera and telescope, and subs you included or excluded by hand."""
    return {
        k: recipe.get(k) for k in ("date_from", "date_to", "datasets", "include", "exclude") if recipe.get(k)
    }


def stackable_with(ds: Dataset, d: Dataset) -> str:
    """Why `d` can't be stacked with `ds`, or '' when it can: same target, filter, camera, telescope and panel, and
    (where both are plate solved) the same framing, at least half the field shared. A mosaic's panels share target,
    filter and rig, so the panel and the framing decide (Heart panel 1 was stacked with panel 2, 2026-10-10)."""
    if (d.target, d.filter_norm, d.camera, d.telescope) != (
        ds.target,
        ds.filter_norm,
        ds.camera,
        ds.telescope,
    ):
        return "its target, filter, camera or telescope differs"
    if (d.panel or None) != (ds.panel or None):
        return f"it is panel {d.panel or 'none'}, not panel {ds.panel or 'none'}"
    from .solving import framing, overlap

    a, b = framing(ds), framing(d)
    if a and b and overlap(b, a) < 0.5:
        return f"its framing shares only {overlap(b, a):.0%} of this one's field"
    return ""


def matching_datasets(ds: Dataset, ids: list[int]) -> list[Dataset]:
    """Other datasets that may be stacked with this one (see stackable_with)."""
    out = []
    for d in Dataset.objects.filter(pk__in=[i for i in ids if i != ds.pk]):
        why = stackable_with(ds, d)
        if why:
            raise ValueError(f"{d.display_name} can't be stacked with this dataset: {why}.")
        out.append(d)
    return out


def candidates(ds: Dataset, nights: list[date] | None, scope: dict | None = None) -> list[Frame]:
    scope = scope or {}
    sets = [ds, *matching_datasets(ds, scope.get("datasets") or [])]
    qs = (
        Frame.objects.filter(dataset__in=sets, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED)
        .select_related("night", "measurement", "grade")
        .prefetch_related("verdicts")
        .order_by("date_obs_utc")
    )
    if nights:
        qs = qs.filter(night__date__in=nights)
    if scope.get("date_from"):
        qs = qs.filter(night__date__gte=scope["date_from"])
    if scope.get("date_to"):
        qs = qs.filter(night__date__lte=scope["date_to"])
    return list(qs)


def choose(
    ds: Dataset, nights: list[date] | None, rule: str, scope: dict | None = None
) -> list[tuple[Frame, bool, float, str]]:
    """(frame, included, weight, reason) for every sub in scope. Subs you included or excluded by hand win over
    the rule, with that as the reason."""
    scope = scope or {}
    include, exclude = set(scope.get("include") or []), set(scope.get("exclude") or [])
    out = []
    for f in candidates(ds, nights, scope):
        try:
            g: MachineGrade | None = f.grade
        except MachineGrade.DoesNotExist:
            g = None
        e = effective(f, list(f.verdicts.all()), g)
        try:
            measured = f.measurement.state == MeasureState.DONE
        except SubMeasurement.DoesNotExist:
            measured = False
        if not measured:
            out.append((f, False, 0.0, "not calibrated yet"))
        elif f.pk in exclude:
            out.append((f, False, 0.0, "excluded by you"))
        elif f.pk in include:
            out.append((f, True, 1.0, "included by you"))
        elif rule == "everything" or rule == "graded":
            out.append((f, True, 1.0 if e.verdict != "down" else e.weight, ""))
        elif rule == "accepted":
            out.append(
                (f, e.verdict == "accept", 1.0, "" if e.verdict == "accept" else f"verdict {e.verdict}")
            )
        else:  # default: effective accepted and down-weighted
            ok = e.verdict in ("accept", "down")
            out.append(
                (
                    f,
                    ok,
                    e.weight if ok else 0.0,
                    ""
                    if ok
                    else ("rejected by you" if e.manual or e.source == "nina" else "rejected by grading"),
                )
            )
    return out


def preview(ds: Dataset, nights: list[date] | None, rule: str, scope: dict | None = None) -> dict:
    chosen = choose(ds, nights, rule, scope)
    inc = [c for c in chosen if c[1]]
    return {
        "subs": len(inc),
        "integration_s": sum(c[0].exptime_s or 0 for c in inc),
        "nights": len({c[0].night_id for c in inc}),
        "excluded": len(chosen) - len(inc),
        "not_calibrated": sum(1 for c in chosen if c[3] == "not calibrated yet"),
        "sharpness_note": sharpness_note([c[0] for c in inc]),
    }


def sharpness_note(frames: list) -> str:  # noqa: ANN001
    """Nights much softer than the sharpest one (focus, seeing) put halos round the sharp stars when stacked
    together (M81 blue, 2026-10-12: 13 Apr at 2.7 px with 18 Apr at 4.3 px). Plain words, not a warning colour."""
    import statistics

    from .models import SubMeasurement

    by_night: dict[str, list[float]] = {}
    rows = SubMeasurement.objects.filter(frame__in=frames, fwhm_px__isnull=False).values_list(
        "frame__night__date", "fwhm_px"
    )
    for night, fwhm in rows:
        if night is not None and fwhm:
            by_night.setdefault(night.strftime("%-d %b"), []).append(float(fwhm))
    med = {n: statistics.median(v) for n, v in by_night.items() if len(v) >= 3}
    if len(med) < 2:
        return ""
    sharp = min(med, key=lambda n: med[n])
    soft = [n for n in med if med[n] > med[sharp] * 1.3]
    if not soft:
        return ""
    worst = max(soft, key=lambda n: med[n])
    return (
        f"{', '.join(soft)} {'is' if len(soft) == 1 else 'are'} much softer than {sharp} "
        f"({med[worst]:.1f} px against {med[sharp]:.1f} px): stacking them together blurs the sharp stars into "
        f"halos. Consider leaving {'it' if len(soft) == 1 else 'them'} out."
    )


def start(
    ds: Dataset,
    nights: list[date] | None,
    rule: str,
    user=None,
    options: dict | None = None,  # noqa: ANN001
    scope: dict | None = None,
) -> Master:
    if rule not in RULES:
        raise ValueError(f"Unknown rule {rule}")
    scope = scope_of(scope or {})
    chosen = choose(ds, nights, rule, scope)
    if sum(1 for c in chosen if c[1]) < 2:
        raise ValueError("Needs at least two calibrated subs.")
    cfg = processing_settings()["stacking"]
    with transaction.atomic():
        version = (
            Master.objects.filter(dataset=ds).order_by("-version").values_list("version", flat=True).first()
            or 0
        ) + 1
        m = Master.objects.create(
            dataset=ds,
            version=version,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            recipe={
                "nights": [n.isoformat() for n in nights] if nights else None,
                "rule": rule,
                "options": cfg | (options or {}),
                **{k: [str(x) for x in v] if k in ("include", "exclude") else v for k, v in scope.items()},
            },
        )
        MasterMember.objects.bulk_create(
            [MasterMember(master=m, frame=f, included=inc, weight=w, reason=why) for f, inc, w, why in chosen]
        )
        inc = [c for c in chosen if c[1]]
        Master.objects.filter(pk=m.pk).update(
            sub_count=len(inc),
            integration_s=sum(c[0].exptime_s or 0 for c in inc),
            session_count=len({c[0].night_id for c in inc}),
        )
    job = enqueue(integrate, m.pk, priority=PRIORITY_BULK + 5)
    Master.objects.filter(pk=m.pk).update(task_id=job.id)
    m.refresh_from_db()
    emit("master.updated", {"dataset_id": ds.pk, "master_id": m.pk, "state": m.state})
    return m


def reconcile_states() -> int:
    """A master whose queue job ended without it (a worker stopped, a job cancelled or retried away in Activity)
    takes the job's outcome, so it never shows "integrating" for ever. Returns masters changed."""
    from substation.tasks.models import Task, TaskStatus

    n = 0
    for m in Master.objects.filter(state__in=[MasterState.QUEUED, MasterState.RUNNING]).exclude(task=None):
        t = Task.objects.filter(pk=str(m.task_id)).values("status", "error", "progress_note").first()
        if t is None or t["status"] in (TaskStatus.READY, TaskStatus.RUNNING):
            continue
        if t["status"] == TaskStatus.CANCELLED:
            state, extra = MasterState.CANCELLED, {"state_reason": m.state_reason or "Cancelled in Activity."}
        else:
            last = (t["error"] or "").strip().splitlines()[-1:] or ["The job stopped without finishing."]
            state, extra = MasterState.FAILED, {"error": m.error or last[0][:500]}
        Master.objects.filter(pk=m.pk).update(state=state, finished_at=timezone.now(), **extra)
        emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": state})
        n += 1
    return n


def _step(m: Master, step: str, progress: float) -> None:
    # PostgreSQL refuses an over-long value (SQLite never did): a long progress line failed a whole stack
    Master.objects.filter(pk=m.pk).update(step=step[:200], progress=progress)
    report_progress(progress, f"Master v{m.version}: {step}")
    emit(
        "master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "step": step, "progress": progress}
    )


class _Live:
    """Live progress inside one long Siril command (004 T004): Siril's "progress: 42%" lines move the master
    between `lo` and `hi`, a normalisation message switches the step to Normalise, and the note carries an
    estimate of the time left from the pace so far."""

    PCT = re.compile(r"progress:\s*([\d.]+)\s*(%?)", re.IGNORECASE)

    def __init__(self, m: Master, step: str, lo: float, hi: float, n: int) -> None:
        self.m, self.step, self.lo, self.hi, self.n = m, step, lo, hi, n
        self.last = 0.0
        self.started = m.started_at or timezone.now()

    def __call__(self, line: str) -> None:
        low = line.lower()
        if self.step == "Integrate" and ("normalis" in low or "normaliz" in low):
            self.step = "Normalise"
        got = self.PCT.search(line)
        if not got:
            return
        frac = float(got.group(1)) / (100 if got.group(2) or float(got.group(1)) > 1 else 1)
        now = time.monotonic()
        if now - self.last < 3:
            return
        self.last = now
        overall = self.lo + (self.hi - self.lo) * min(max(frac, 0.0), 1.0)
        done = f" {round(frac * self.n)}/{self.n}" if self.n and self.step == "Register" else f" {frac:.0%}"
        spent = (timezone.now() - self.started).total_seconds()
        left = spent * (1 - overall) / overall if overall > 0.05 else None
        eta = f" · about {left / 60:.0f} min left" if left and left > 60 else ""
        Master.objects.filter(pk=self.m.pk).update(step=self.step, progress=overall)
        report_progress(overall, f"Master v{self.m.version}: {self.step}{done}{eta}")


def _inputs(m: Master, members: list[MasterMember], work: Path) -> dict[int, MasterMember]:
    """Each member's calibrated sub, linked as work/sub_NNNNN.fit. Subs whose cached calibration was pruned are
    calibrated again in batches (calibrate_batch) into this stack's own folder."""
    order: dict[int, MasterMember] = {}
    redo = work / "recal"
    pending: list[tuple[int, MasterMember]] = []  # pruned from the cache: calibrated again below
    for i, mm in enumerate(members, start=1):
        cal = Path(mm.frame.measurement.calibrated_path) if mm.frame.measurement.calibrated_path else None
        if cal is not None and cal.exists():
            os.symlink(cal, work / f"sub_{i:05d}.fit")
            order[i] = mm
        else:
            pending.append((i, mm))
    if pending:
        # into this stack's own folder: written back to the shared cache, a recalibrated sub could be pruned by
        # other workers while this stack still reads it (2026-10-13)
        failed = recalibrate(
            [(mm.frame, redo / f"sub_{i:05d}.fit") for i, mm in pending],
            redo,
            lambda note, frac: _step(m, note, 0.1 + 0.1 * frac),
        )
        for i, mm in pending:
            if mm.frame_id in failed:
                mm.included, mm.reason = False, failed[mm.frame_id]
                mm.save(update_fields=["included", "reason"])
                continue
            os.symlink(redo / f"sub_{i:05d}.fit", work / f"sub_{i:05d}.fit")
            order[i] = mm
    return dict(sorted(order.items()))


def recalibrate(items: list[tuple[Frame, Path]], redo: Path, step=None) -> dict[str, str]:  # noqa: ANN001
    """Calibrate subs whose cached calibration was pruned again, each into its given file under `redo`: in batches
    (calibrate_batch), then one at a time for what a batch couldn't do. `step(note, fraction)` reports progress.
    Returns the subs that couldn't be calibrated, with why (frame sha → reason)."""
    from .models import CalibrationMatch, MatchState
    from .tasks import calibrate_batch, calibrate_file, source_path

    failed: dict[str, str] = {}
    todo: list = []  # (frame, match, source, where the result goes)
    for frame, out in items:
        cm = CalibrationMatch.objects.filter(frame=frame, state=MatchState.MATCHED).first()
        src = source_path(frame)
        if cm is None or src is None:
            failed[frame.pk] = "no copy on disk" if src is None else "no longer matched"
            continue
        todo.append((frame, cm, src, out))
    if not todo:
        return failed
    if step:
        step(f"Calibrate ({len(todo)} subs)", 0.0)
    redo.mkdir(parents=True, exist_ok=True)
    left = {f.pk for f in calibrate_batch(todo, redo)}
    for k, (frame, cm, src, out) in enumerate(todo, start=1):
        if frame.pk in left:  # one at a time, as before
            calibrate_file(frame, cm, src, redo, out)
        if k % 10 == 0 and step:
            step(f"Calibrate ({k} of {len(todo)})", k / len(todo))
    return failed


MOSAIC_SPREAD = 0.5  # subs whose centres stray more than half the field's short side make a mosaic


def mosaic_reason(frames: list[Frame]) -> str | None:
    """Why these subs are a mosaic, or None (004-DR-23). Seestar's mosaic mode moves the field around a grid every
    few subs (IC 4605: 249 pointings over about 4°), so there are no panels to split: subs far apart share too few
    stars for one reference, and the stack has to be registered by plate solution onto one canvas instead. Decided
    from the subs' solves; without enough solves, from Seestar's "_mosaic" file names."""
    import math
    import statistics

    from .models import PlateSolve, SolveState

    solves: list[tuple[float, float, float, float]] = [
        (a, b, c, d)
        for a, b, c, d in PlateSolve.objects.filter(frame__in=frames, state=SolveState.SOLVED).values_list(
            "ra_deg", "dec_deg", "fov_w_deg", "fov_h_deg"
        )
        if a is not None and b is not None and c is not None and d is not None
    ]
    if len(solves) >= max(3, len(frames) // 2):
        ra0 = statistics.median(r[0] for r in solves)
        dec0 = statistics.median(r[1] for r in solves)
        short = statistics.median(min(r[2], r[3]) for r in solves)

        def sep(ra: float, dec: float) -> float:
            dra = (ra - ra0 + 180) % 360 - 180
            return math.hypot(dra * math.cos(math.radians(dec0)), dec - dec0)

        seps = [sep(r[0], r[1]) for r in solves]
        # a stray sub (a slew or framing test, 2.9° off on M 42 L, 2026-10-15) doesn't make a mosaic: enough of
        # them must sit away from the middle that the field really moves
        away = [d for d in seps if short and d > MOSAIC_SPREAD * short]
        if short and len(away) >= max(2, len(seps) // 10):
            return f"Mosaic: the subs' centres spread {max(away):.1f}° across a {short:.1f}° field"
        return None
    names = [c.rel_path.rsplit("/", 1)[-1].lower() for c in Copy.objects.filter(frame__in=frames)]
    if names and sum("_mosaic_" in n for n in names) > len(names) / 2:
        return "Mosaic: Seestar mosaic subs"
    return None


def _reject_unregistered(m: Master, shas: list[str], mosaic: bool = False) -> None:
    """A sub whose stars can't be matched to the reference becomes a Rejected auto grade with the reason (spec
    003 US1/AC4), so Review shows it instead of it silently dropping out of every stack. Human verdicts still win."""
    if not shas:
        return
    from .effective import recount_grades
    from .models import GradeVerdict, MachineGrade

    MachineGrade.objects.filter(frame_id__in=shas).update(
        verdict=GradeVerdict.REJECT,
        weight=0.0,
        near_threshold=False,
        reason=(
            "Couldn't register: no plate solution for this sub."
            if mosaic
            else "Couldn't register: too few stars matched the reference."
        ),
    )
    recount_grades(m.dataset)


def _regional(path: Path, stars: list) -> dict:
    from astropy.io import fits

    from apps.engine import parse

    h = fits.getheader(path)
    return parse.regional(stars, int(h.get("NAXIS1") or 0), int(h.get("NAXIS2") or 0))


def fits_ascii(text: str) -> str:
    """FITS headers take printable ASCII only: a note with "°" failed a finished stack at its last step."""
    import unicodedata

    for a, b in (
        ("°", " deg"),
        ("α", "a"),
        ("β", "b"),
        ("×", "x"),
        ("−", "-"),
        ("–", "-"),
        ("—", "-"),
        ("″", '"'),
        ("′", "'"),
        ("·", "-"),
        ("…", "..."),
    ):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in text if 32 <= ord(c) < 127)


def _provenance(path: Path, m: Master, notes: list[str]) -> None:
    """Write where the master came from into its own header (spec 004 FR-009), so the file explains itself."""
    from astropy.io import fits
    from django.db.models import Max, Min, Sum

    inc = MasterMember.objects.filter(master=m, included=True)
    agg = inc.aggregate(
        first=Min("frame__date_obs_utc"), last=Max("frame__date_obs_utc"), exp=Sum("frame__exptime_s")
    )
    o = m.recipe.get("options", {})
    with fits.open(path, mode="update") as hl:
        h = hl[0].header
        h["CREATOR"] = ("SubStation", "integrated by SubStation with Siril")
        h["SST-MSTR"] = (f"v{m.version}", "SubStation master version")
        h["NCOMBINE"] = (inc.count(), "subs integrated")
        if agg["exp"]:
            h["TOTEXP"] = (round(agg["exp"], 1), "[s] total exposure of the subs")
        if agg["first"]:
            h["DATE-BEG"] = (agg["first"].strftime("%Y-%m-%dT%H:%M:%S"), "first sub (UTC)")
        if agg["last"]:
            h["DATE-END"] = (agg["last"].strftime("%Y-%m-%dT%H:%M:%S"), "last sub (UTC)")
        h["SST-RULE"] = (str(m.recipe.get("rule", "default"))[:60], "which subs were chosen")
        h["SST-REJ"] = (
            f"{o.get('rejection', 'winsorized')} {' '.join(str(x) for x in o.get('sigma', [3, 3]))}"[:60],
            "pixel rejection",
        )
        h["SST-WGT"] = (str(o.get("weighting", "grade"))[:60], "sub weighting")
        if resolution_of(m) != "normal":
            h["SST-RES"] = (fits_ascii(RESOLUTIONS[resolution_of(m)]), "drizzled or binned (SubStation)")
        for n in notes:
            h.add_history(fits_ascii(n)[:70])


def work_budget_bytes() -> float:
    """The stacking work budget: Settings → Workers, else STACK_WORK_BUDGET_GB (005 T004)."""
    from apps.libraries.models import InstallationSettings

    gb = InstallationSettings.load().work_budget_gb
    return (gb if gb else settings.STACK_WORK_BUDGET_GB) * 1e9


def _dir_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            with contextlib.suppress(OSError):
                fp = Path(dirpath) / name
                if not fp.is_symlink():
                    total += fp.stat().st_size
    return total


def _check_budget(work: Path, n: int, grow: int = 1) -> None:
    """The subs plus one registered copy each must fit the stack work budget (004 T015); drizzled ×2, each
    registered copy is `grow` (4) times a sub (004-DR-35). A stack that can never fit fails with the reason; one
    that would fit once other stacks' working files are gone waits for them."""
    first = next(iter(sorted(work.glob("sub_*.fit*"))), None)
    if first is None:
        return
    need = first.resolve().stat().st_size * n * (1 + grow)
    budget = work_budget_bytes()
    if need > budget:
        why = (
            " Drizzle ×2 makes every registered sub four times the size; stack without it, or fewer sessions."
            if grow > 1
            else " Stack fewer sessions or raise the budget in Settings → Workers."
        )
        raise RuntimeError(
            f"Needs about {need / 1e9:.0f} GB of working space for {n} subs; the work budget is "
            f"{budget / 1e9:.0f} GB.{why}"
        )
    others = sum(_dir_bytes(d) for d in (Path(settings.WORK_DIR) / "integrations").glob("*") if d != work)
    if need + others > budget and _kept_folders(
        work
    ):  # folders kept for a retry give way to a stack that runs
        _release_kept(work)
        others = sum(_dir_bytes(d) for d in (Path(settings.WORK_DIR) / "integrations").glob("*") if d != work)
    if need + others > budget:
        raise Reschedule(
            600,
            f"Waiting for disk space: needs {need / 1e9:.0f} GB, other stacks use "
            f"{others / 1e9:.0f} of {budget / 1e9:.0f} GB.",
        )


def _fit_registered(eng, work: Path, n: int, grow: int = 1) -> list[str]:  # noqa: ANN001
    """Siril refuses to write the registered subs unless the free space it sees covers them. Under Docker Desktop
    that is the Mac's system disk, whatever disk the folder is really on, so a large stack can be refused with
    hundreds of GB free. Registered subs are saved at 16 bits when 32 won't fit (half the size; the stack itself is
    still 32-bit), and the stack stops with the reason if neither fits."""
    first = next(iter(sorted(work.glob("sub_*.fit*"))), None)
    if first is None:
        return []
    from astropy.io import fits

    if fits.getheader(first.resolve()).get("BITPIX") == 16:
        eng.run(
            "set16bits"
        )  # 16-bit subs (in-camera calibrated, just debayered) gain nothing from float copies
        return ["Registered subs kept at 16 bits."]
    need = first.resolve().stat().st_size * n * 1.1 * grow  # a drizzled copy is four times a sub
    free = shutil.disk_usage(work).free
    if need <= free:
        return []
    if need / 2 <= free:
        eng.run("set16bits")
        return [
            f"Registered subs saved at 16 bits: {free / 1e9:.0f} GB free, 32-bit needed {need / 1e9:.0f} GB."
        ]
    raise RuntimeError(
        f"Not enough space to register {n} subs: needs {need / 2e9:.0f} GB at 16 bits, "
        f"{free / 1e9:.0f} GB free (Mac system disk under Docker Desktop). Free space or stack fewer sessions."
    )


def _write_wcs(path: Path, wcs: dict) -> bool:
    """Write a stored plate solution into the stack's own copy of a sub (replacing the link to the cached
    calibrated file, so the cache is never written to). Only when the image is the size the solution was made for."""
    from astropy.io import fits

    try:
        src = path.resolve()
        with fits.open(src, memmap=False) as hdul:
            h = hdul[0].header
            size = (h.get("NAXIS1"), h.get("NAXIS2"))
            if size != (wcs.get("NAXIS1"), wcs.get("NAXIS2")):
                # a sub binned 2×2 for this stack (004-DR-35): its solution, on the coarser grid
                if wcs.get("NAXIS1") is None or size != (int(wcs["NAXIS1"]) // 2, int(wcs["NAXIS2"]) // 2):
                    return False
                wcs = scaled_wcs(wcs, 2)
            data, header = hdul[0].data, h.copy()
        for k, v in wcs.items():
            if not k.startswith("NAXIS"):
                header[k] = v
        header["PLTSOLVD"] = (True, "plate solved by SubStation on arrival")
        tmp = path.with_suffix(".part.fit")
        fits.PrimaryHDU(data=data, header=header).writeto(tmp, overwrite=True)
        path.unlink(missing_ok=True)
        tmp.replace(path)
        return True
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Couldn't write the stored solution into %s: %s", path.name, exc)
        return False


def _keep_wcs(path: Path, frame_id: str) -> None:
    """Keep the solution Siril just made for a sub, so the next stack reuses it (004-DR-26)."""
    from astropy.io import fits

    from .models import PlateSolve, SolveState
    from .solving import WCS_KEYS

    try:
        h = fits.getheader(path)
    except (OSError, ValueError):
        return
    wcs = {k: h[k] for k in h if WCS_KEYS.match(k) and not isinstance(h[k], bool | type(None))}
    if "CRVAL1" not in wcs:
        return
    if not PlateSolve.objects.filter(frame_id=frame_id, state=SolveState.SOLVED).update(wcs=wcs):
        # it didn't solve on arrival (downscaled, too few stars): it has now, at full resolution
        PlateSolve.objects.update_or_create(
            frame_id=frame_id,
            defaults={
                "state": SolveState.SOLVED,
                "ra_deg": float(wcs["CRVAL1"]),
                "dec_deg": float(wcs["CRVAL2"]),
                "source": "calibrated",
                "reason": "",
                "wcs": wcs,
            },
        )


def _solve_each(eng, work: Path, order: dict[int, MasterMember], m: Master) -> tuple[list[int], list[int]]:  # noqa: ANN001
    """Plate solve every sub on its own (004-DR-23). A sub solved on arrival already has its whole solution stored,
    which is written into the stack's own copy instead of solving it again (004-DR-26); the rest are solved here at
    full resolution (downscaled, a 10 s Seestar sub shows too few stars), and their solutions kept for next time.
    A sub Siril can't solve, or that crashes it, is left out; Siril starts again for the next one."""
    from apps.engine.siril import EngineError

    from .models import PlateSolve, SolveState

    stored = dict(
        PlateSolve.objects.filter(
            frame_id__in=[mm.frame_id for mm in order.values()], state=SolveState.SOLVED
        )
        .exclude(wcs={})
        .values_list("frame_id", "wcs")
    )
    solved: list[int] = []
    unsolved: list[int] = []
    reused = 0
    n = len(order)
    for k, i in enumerate(sorted(order), start=1):
        name = f"sub_{i:05d}"
        wcs = stored.get(order[i].frame_id)
        if wcs and _write_wcs(work / f"{name}.fit", wcs):
            solved.append(i)
            reused += 1
        else:
            try:
                eng.run(f"cd {work}")
                eng.run(f"load {name}", timeout=180)
                if eng.run("platesolve -force", timeout=180, check=False).ok:
                    # a link to the cache: write our own copy instead
                    (work / f"{name}.fit").unlink(missing_ok=True)
                    eng.run(f"save {name}", timeout=180)
                    solved.append(i)
                    if resolution_of(m) != "bin2":  # a binned sub's solution isn't the sub's own
                        _keep_wcs(work / f"{name}.fit", order[i].frame_id)
                else:
                    unsolved.append(i)
            except EngineError as exc:  # Siril crashed on this sub: the next command starts it again
                log.warning("Plate solving %s failed: %s", name, exc)
                unsolved.append(i)
        if k % 10 == 0 or k == n:
            _step(m, f"Plate solve ({k} of {n}, {reused} already solved)", 0.2 + 0.25 * k / n)
    return solved, unsolved


def _mark_kept(work: Path, master_pk: int) -> bool:
    """A failed or cancelled stack keeps its folder for KEPT_FOR when it got as far as its inputs (004-DR-27)."""
    ck = _checkpoint(work, master_pk)
    if "inputs" not in ck["done"]:
        return False
    ck["kept"] = time.time()
    _save_checkpoint(work, ck)
    return True


def _checkpoint(work: Path, master_pk: int) -> dict:
    """What an earlier, interrupted run of this master finished (005-DR-25); nothing when there was none."""
    import json

    try:
        ck = json.loads((work / "checkpoint.json").read_text())
    except (OSError, ValueError):
        return {"master": master_pk, "done": []}
    return ck if ck.get("master") == master_pk else {"master": master_pk, "done": []}


def _save_checkpoint(work: Path, ck: dict) -> None:
    import json

    tmp = work / "checkpoint.json.part"
    tmp.write_text(json.dumps(ck))
    tmp.replace(work / "checkpoint.json")


def _resumed_inputs(work: Path, ck: dict, m: Master | None = None) -> dict[int, MasterMember] | None:
    """The inputs an interrupted run had linked, if every one is still there; else None (start again). A folder kept
    from another version of the stack is matched to this one's members by frame."""
    order = {}
    frames = ck.get("frames") or {}
    for i, pk in (ck.get("order") or {}).items():
        q = MasterMember.objects.select_related("frame__measurement")
        mm = (
            q.filter(master=m, frame_id=frames[i]).first()
            if m is not None and i in frames
            else q.filter(pk=pk).first()
        )
        if mm is None or not (work / f"sub_{int(i):05d}.fit").exists():
            return None
        order[int(i)] = mm
    return order or None


KEPT_FOR = timedelta(days=3)  # a failed or cancelled stack's folder, kept for a retry or rerun (004-DR-27)


def _kept_folders(skip: Path) -> list[tuple[Path, dict]]:
    import json

    out = []
    for d in (Path(settings.WORK_DIR) / "integrations").glob("ds*_v*"):
        if d == skip:
            continue
        try:
            ck = json.loads((d / "checkpoint.json").read_text())
        except (OSError, ValueError):
            continue
        if ck.get("kept"):
            out.append((d, ck))
    return out


def _release_kept(skip: Path, older_than: timedelta | None = None) -> None:
    """Delete kept folders: all of them when another stack needs the room, or those past KEPT_FOR."""
    now = time.time()
    for d, ck in _kept_folders(skip):
        if older_than is None or now - float(ck["kept"]) > older_than.total_seconds():
            shutil.rmtree(d, ignore_errors=True)


def _adopt(work: Path, m: Master, members: list[MasterMember]) -> dict | None:
    """A rerun takes over the folder kept from an earlier version of this dataset's stack when it was made from
    the same subs, and carries on from what that one finished (its solves, its registration)."""
    want = sorted(mm.frame_id for mm in members)
    for d, ck in _kept_folders(work):
        if not d.name.startswith(f"ds{m.dataset_id}_v") or sorted((ck.get("frames") or {}).values()) != want:
            continue
        if (ck.get("resolution") or "normal") != resolution_of(m):  # binned or drizzled another way
            continue
        shutil.rmtree(work, ignore_errors=True)
        d.rename(work)
        ck.update(master=m.pk, kept=None)
        ck.setdefault("notes", []).append(f"Carried on from the folder kept from {d.name.split('_')[-1]}.")
        _save_checkpoint(work, ck)
        return ck
    return None


def _open_work(m: Master) -> tuple[Path, dict]:
    """The stack's work folder and its checkpoint. 005-DR-25: a stack stopped by a redeploy resumes from what it
    had finished (its inputs, its registration); with nothing finished the folder starts empty. A folder kept
    from a failed or cancelled run is in use again, so nothing may release it."""
    work = Path(settings.WORK_DIR) / "integrations" / f"ds{m.dataset_id}_v{m.version}"
    ck = _checkpoint(work, m.pk)
    if ck.get("kept"):
        ck["kept"] = None
        _save_checkpoint(work, ck)
    if not ck["done"]:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
    return work, ck


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def integrate(master_id: int) -> dict:
    from apps.engine import parse
    from apps.engine.siril import engine, heavy_memory

    m = Master.objects.select_related("dataset").get(pk=master_id)
    if m.state == MasterState.CANCELLED:
        return {"result": "cancelled"}
    Master.objects.filter(pk=m.pk).update(state=MasterState.RUNNING, started_at=timezone.now(), error=None)
    work, ck = _open_work(m)
    keep = False
    try:
        members, order, ck = _prepare_inputs(m, work, ck)
        check_interrupted()
        if len(order) < 2:
            raise RuntimeError("Fewer than two calibrated subs.")
        res = resolution_of(m)
        if res == "bin2":
            _bin_inputs(m, work, ck, order)
        eng = engine()
        _heavy = heavy_memory()
        _heavy.__enter__()
        eng.run(f"cd {work}")
        _step(m, "Register", 0.2)
        _check_budget(work, len(order), 4 if res == "drizzle2" else 1)
        mosaic = mosaic_reason([mm.frame for mm in order.values()])
        notes = _register(eng, m, work, ck, order, mosaic)
        notes += resolution_notes(m, order)
        eng.run("set32bits")
        registered = {im["filenum"] for im in parse.seq_images(work / "r_sub_.seq")}
        _exclude_unregistered(m, order, registered, mosaic)
        _step(m, "Integrate", 0.6)
        out_dir = _stacks_dir(m)
        out = out_dir / f"master_v{m.version}"
        stack = eng.run(
            _stack_command(m, order, notes, mosaic, out),
            timeout=7200,
            quiet=True,
            on_line=_Live(m, "Integrate", 0.6, 0.9, len(order)),
        )
        _step(m, "Write", 0.9)
        result = out.with_suffix(".fit")
        _provenance(result, m, notes)
        report, prev = _measure_master(
            eng, m, work, result, out_dir, members, order, registered, stack, notes
        )
        _make_current(m, eng, result, prev, report)
    except Interrupted:
        keep = True  # its work folder is where it resumes from
        Master.objects.filter(pk=m.pk).update(
            state=MasterState.QUEUED, state_reason="Stopped by a restart; resumes where it left off."
        )
        raise
    except Reschedule as r:
        Master.objects.filter(pk=m.pk).update(state=MasterState.QUEUED, state_reason=r.note)
        raise
    except Cancelled:
        keep = _mark_kept(work, m.pk)
        reason = Master.objects.filter(pk=m.pk).values_list("state_reason", flat=True).first() or "Cancelled."
        Master.objects.filter(pk=m.pk).update(
            state=MasterState.CANCELLED, state_reason=reason, finished_at=timezone.now()
        )
        emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": "cancelled"})
        raise
    except Exception as exc:
        keep = _mark_kept(work, m.pk)
        Master.objects.filter(pk=m.pk).update(
            state=MasterState.FAILED, error=str(exc), finished_at=timezone.now()
        )
        emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": "failed"})
        raise
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
        if "_heavy" in locals():
            _heavy.__exit__(None, None, None)
    emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": "current"})
    _after_stack(m)
    return {"master": m.pk, "subs": len(registered)}


def _prepare_inputs(
    m: Master, work: Path, ck: dict
) -> tuple[list[MasterMember], dict[int, MasterMember], dict]:
    """The included subs, linked into the work folder in a fixed order; a resumed or adopted folder keeps its own."""
    _step(m, "Select inputs", 0.02)
    members = list(
        MasterMember.objects.filter(master=m, included=True)
        .select_related("frame__measurement")
        .order_by("pk")
    )
    cached = [
        Path(mm.frame.measurement.calibrated_path) for mm in members if mm.frame.measurement.calibrated_path
    ]
    for p in cached:  # newest in the cache, so pruning doesn't take them mid-integration
        with contextlib.suppress(FileNotFoundError):
            os.utime(p)
    _step(m, "Calibrate", 0.1)  # done on arrival; subs pruned from the cache are calibrated again here
    _release_kept(work, KEPT_FOR)
    if not ck["done"]:
        ck = _adopt(work, m, members) or ck
    same = (ck.get("resolution") or "normal") == resolution_of(m)
    order = _resumed_inputs(work, ck, m) if "inputs" in ck["done"] and same else None
    if order is None:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        ck = {"master": m.pk, "done": [], "resolution": resolution_of(m)}
        order = _inputs(m, members, work)
        ck.update(
            done=["inputs"],
            order={str(i): mm.pk for i, mm in order.items()},
            frames={str(i): mm.frame_id for i, mm in order.items()},
        )
        _save_checkpoint(work, ck)
    return members, order, ck


def _register(
    eng, m: Master, work: Path, ck: dict, order: dict[int, MasterMember], mosaic: str | None
) -> list[str]:  # noqa: ANN001
    """Register the subs (or reuse a registration made the same way); returns the notes for the report."""
    # a registration is reused only if made the same way (a kept folder registered as a mosaic under an
    # older rule had carried its canvas into a normal stack)
    if "registered" in ck["done"] and ck.get("mosaic") != bool(mosaic):
        ck["done"].remove("registered")
    if "registered" in ck["done"] and (work / "r_sub_.seq").exists():
        notes = list(ck.get("notes", []))
        notes.append("Resumed after a restart: registration was already done.")
    elif mosaic:
        notes = _register_mosaic(eng, m, work, order, mosaic)
    elif (m.recipe.get("options") or {}).get("reference") == "most_stars":
        # the sub with the most stars is the reference; one pass keeps that choice (004 FR-004)
        best = max(order, key=lambda i: order[i].frame.measurement.stars or 0)
        notes = _fit_registered(eng, work, len(order), _grow(m))
        eng.run(f"setref sub_ {sorted(order).index(best) + 1}")
        eng.run(
            f"register sub_{_drizzle(m)}",
            timeout=7200,
            quiet=True,
            on_line=_Live(m, "Register", 0.2, 0.6, len(order)),
        )
        notes.append(f"Reference: sub with most stars ({order[best].frame.measurement.stars:,}).")
    else:
        # two passes: Siril picks the sharpest, roundest sub as the reference (best FWHM)
        eng.run(
            "register sub_ -2pass",
            timeout=7200,
            quiet=True,
            on_line=_Live(m, "Register", 0.2, 0.4, len(order)),
        )
        notes = _fit_registered(eng, work, len(order), _grow(m))
        eng.run(
            f"seqapplyreg sub_ -framing=current{_drizzle(m)}",
            timeout=7200,
            quiet=True,
            on_line=_Live(m, "Register", 0.4, 0.6, len(order)),
        )
    if "registered" not in ck["done"]:
        ck["done"].append("registered")
        ck["mosaic"] = bool(mosaic)
        ck["notes"] = notes
        _save_checkpoint(work, ck)
    return notes


def _drizzle(m: Master) -> str:
    """Siril's drizzle options for a master stacked Drizzle ×2, else nothing."""
    return f" {DRIZZLE}" if resolution_of(m) == "drizzle2" else ""


def _grow(m: Master) -> int:
    return 4 if resolution_of(m) == "drizzle2" else 1


def resolution_notes(m: Master, order: dict[int, MasterMember]) -> list[str]:
    """What the report says about a drizzled or binned master (004-DR-35)."""
    from .tasks import is_colour_frame

    res = resolution_of(m)
    if res == "drizzle2":
        notes = ["Drizzle ×2 (pixel fraction 1, square kernel): twice the width and height of the subs."]
        first = next(iter(order.values()), None)
        if first is not None and is_colour_frame(first.frame):
            notes.append(
                "Colour subs are debayered when they are calibrated, so this drizzles the debayered subs; it is "
                "not a Bayer drizzle."
            )
        return notes
    if res == "bin2":
        return [
            "Bin 2×2: each 2×2 block of the calibrated subs averaged before registration (half the size)."
        ]
    return []


def _register_mosaic(eng, m: Master, work: Path, order: dict[int, MasterMember], mosaic: str) -> list[str]:  # noqa: ANN001
    """Register by plate solution onto one canvas that holds every sub (004-DR-23). Each sub is solved on its own
    first: a sub that crashes Siril (IC 4605, 2026-10-14: a segfault at sub 284 of 413 took the whole stack down)
    costs only itself; seqplatesolve then lays out the canvas from those solutions."""
    notes = _fit_registered(eng, work, len(order), _grow(m))
    solved, unsolved = _solve_each(eng, work, order, m)
    if len(solved) < 2:
        raise RuntimeError(f"Only {len(solved)} of {len(order)} subs could be plate solved.")
    eng.run(f"cd {work}")
    for i in unsolved:  # positions in the sequence, not file numbers (subs can be missing from the run)
        at = sorted(order).index(i) + 1
        eng.run(f"unselect sub_ {at} {at}", check=False)
    eng.run(
        "seqplatesolve sub_", timeout=7200, quiet=True, on_line=_Live(m, "Plate solve", 0.45, 0.5, len(order))
    )
    eng.run(
        f"seqapplyreg sub_ -framing=max{_drizzle(m)}",
        timeout=7200,
        quiet=True,
        on_line=_Live(m, "Register", 0.5, 0.6, len(order)),
    )
    notes.append(f"{mosaic}: registered by plate solution and stacked onto one canvas.")
    if unsolved:
        notes.append(f"{len(unsolved)} sub{'s' if len(unsolved) != 1 else ''} couldn't be plate solved.")
    return notes


def _exclude_unregistered(
    m: Master, order: dict[int, MasterMember], registered: set[int], mosaic: str | None
) -> None:
    unmatched = []
    for i, mm in order.items():
        if i not in registered:
            mm.included, mm.reason = (False, ("could not plate solve" if mosaic else "could not match stars"))
            mm.save(update_fields=["included", "reason"])
            unmatched.append(mm.frame_id)
    _reject_unregistered(m, unmatched, mosaic=bool(mosaic))


def _stacks_dir(m: Master) -> Path:
    out_dir = Path(settings.STACKS_DIR) / f"ds{m.dataset_id}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"Can't write to {settings.STACKS_DIR} ({exc.strerror or exc}). Check the stacks volume "
            "is writable and has room, then retry."
        ) from None
    return out_dir


def _stack_command(
    m: Master, order: dict[int, MasterMember], notes: list[str], mosaic: str | None, out: Path
) -> str:
    """Siril's stack command from the recipe; a note is added when mixed exposures change the weighting."""
    exposures = {round(mm.frame.exptime_s or 0, 3) for mm in order.values() if mm.included}
    # a mosaic: the canvas holds every sub; levels match on the overlaps and edges blend
    canvas = " -maximize -overlap_norm -feather=100" if mosaic else ""
    opts = stack_options(m.recipe.get("options", {}), exposures, notes)
    return f"stack r_sub_ {opts}{canvas} -out={out} -32b".replace("  ", " ")


def stack_options(cfg: dict, exposures: set[float], notes: list[str], rejection: bool = True) -> str:
    """Rejection, normalisation and weighting for Siril's stack command, from stacking options (a master's recipe
    or Settings → Stacking); `rejection` False stacks without it (too few subs to reject from)."""
    lo, hi = (cfg.get("sigma") or [3.0, 3.0])[:2]
    weight = {"grade": "-weight=wfwhm", "snr": "-weight=noise", "equal": ""}.get(
        cfg.get("weighting", "grade"), ""
    )
    # mixed exposures (owner 2026-10-13): weight by noise (inverse
    # variance), so a 240 s sub counts for about four 60 s ones; sharpness weighting ignores exposure
    if weight == "-weight=wfwhm" and len(exposures) > 1:
        weight = "-weight=noise"
        notes.append(
            "Mixed exposures ("
            + ", ".join(f"{e:g} s" for e in sorted(exposures))
            + "): weighted by noise, so longer subs count for more."
        )
    rej = {"winsorized": "w", "sigma": "s", "linear": "l"}.get(cfg.get("rejection", "winsorized"), "w")
    rejecting = f"rej {rej} {lo:g} {hi:g}" if rejection else "rej n"
    return f"{rejecting} -norm=addscale {weight}"


def _measure_master(
    eng,  # noqa: ANN001
    m: Master,
    work: Path,
    result: Path,
    out_dir: Path,
    members: list[MasterMember],
    order: dict[int, MasterMember],
    registered: set[int],
    stack,  # noqa: ANN001
    notes: list[str],
) -> tuple[dict, Path]:
    """Stars, sharpness and noise of the finished master, and its preview."""
    from apps.engine import parse

    from .previews import render
    from .tasks import pixel_scale

    eng.run(f"load {result}")
    n, fwhm = parse.found_stars(eng.run(f"findstar -out={work / 'stars.lst'}").log)
    noise = parse.bgnoise(eng.run("bgnoise").log)
    stars = parse.star_list(work / "stars.lst")
    prev = out_dir / f"master_v{m.version}.jpg"
    try:
        render(result, prev, out_dir / f"master_v{m.version}_t.jpg")
    except Exception as exc:  # noqa: BLE001
        log.warning("Master preview failed: %s", exc)
    scale = pixel_scale(members[0].frame)
    if scale:
        scale *= pixel_factor(resolution_of(m))  # a drizzled or binned master's pixels (004-DR-35)
    report = {
        "stars": n,
        "fwhm_px": fwhm,
        "fwhm_arcsec": fwhm * scale if fwhm and scale else None,
        "roundness": parse.roundness(stars),
        "noise": noise,
        "excluded_registration": len(order) - len(registered & set(order)),
        "stack_log": [line for line in stack.log if "stacked" in line or "rejection" in line.lower()][-4:],
        "notes": notes,
        "regional": _regional(result, stars),
    }
    return report, prev


def _superseded_reason(m: Master, old: Master, n_new: int) -> str:
    diff = n_new - old.sub_count
    why = (
        f" ({diff} more sub{'s' if diff != 1 else ''})"
        if diff > 0
        else (f" ({-diff} fewer sub{'s' if diff != -1 else ''})" if diff < 0 else "")
    )
    return f"Replaced by v{m.version}{why}."


def _make_current(m: Master, eng, result: Path, prev: Path, report: dict) -> None:  # noqa: ANN001
    """The new master becomes current; the ones it replaces say why; the owner is told."""
    included = MasterMember.objects.filter(master=m, included=True).select_related("frame")
    with transaction.atomic():
        n_new = included.count()
        for old in Master.objects.filter(
            dataset=m.dataset, state__in=[MasterState.CURRENT, MasterState.STALE]
        ):
            Master.objects.filter(pk=old.pk).update(
                state=MasterState.SUPERSEDED, state_reason=_superseded_reason(m, old, n_new)
            )
        Master.objects.filter(pk=m.pk).update(
            state=MasterState.CURRENT,
            step="Done",
            progress=1.0,
            output_path=str(result),
            preview_path=str(prev) if prev.exists() else "",
            report=report,
            finished_at=timezone.now(),
            engine_version=eng.version,
            sub_count=included.count(),
            integration_s=sum(mm.frame.exptime_s or 0 for mm in included),
            session_count=included.values("frame__night").distinct().count(),
        )
    from substation.notify import send

    send(
        "master_finished",
        f"Master v{m.version} is ready",
        f"{m.dataset.display_name}: {included.count()} subs, FWHM {report['fwhm_arcsec']:.2f}″."
        if report.get("fwhm_arcsec")
        else f"{m.dataset.display_name}: {included.count()} subs.",
    )


def _after_stack(m: Master) -> None:
    """Plate solve the master, make its views, and run the finishing chain when it's switched on."""
    from .config import processing_settings
    from .solving import solve_master
    from .tasks import master_view

    enqueue(solve_master, m.pk, dedupe_key=f"solve-master:{m.pk}")
    enqueue(master_view, m.pk, dedupe_key=f"master-view:{m.pk}")
    post = processing_settings()["post"]
    # spec 010: the finishing chain, when switched on (globally, or for this dataset when stacking)
    if (m.report or {}).get("post_override", {}).get("enabled", post.get("enabled")):
        from .postprocess import postprocess_master

        enqueue(postprocess_master, m.pk, (m.report or {}).get("post_override"), dedupe_key=f"post:{m.pk}")


def check_stale(ds: Dataset) -> None:
    """A current master whose inclusion list would now differ is Stale, with the reason (spec 004 US4)."""
    for m in Master.objects.filter(dataset=ds, state=MasterState.CURRENT):
        nights = [date.fromisoformat(n) for n in (m.recipe.get("nights") or [])] or None
        now = {
            c[0].pk for c in choose(ds, nights, m.recipe.get("rule", "default"), scope_of(m.recipe)) if c[1]
        }
        then = set(
            MasterMember.objects.filter(master=m)
            .exclude(reason__in=["could not match stars", "could not plate solve"])
            .filter(included=True)
            .values_list("frame_id", flat=True)
        )
        then |= set(
            MasterMember.objects.filter(
                master=m, reason__in=["could not match stars", "could not plate solve"]
            ).values_list("frame_id", flat=True)
        )
        new, gone = now - then, then - now
        if new or gone:
            parts = []
            if new:
                parts.append(
                    f"{len(new)} new sub{'s' if len(new) != 1 else ''} since {m.finished_at:%-d %B}"
                    if m.finished_at
                    else f"{len(new)} new subs"
                )
            if gone:
                parts.append(f"{len(gone)} sub{'s' if len(gone) != 1 else ''} no longer included")
            Master.objects.filter(pk=m.pk).update(
                state=MasterState.STALE, state_reason="; ".join(parts) + "."
            )


def _measured_since_last_master(ds: Dataset) -> list[SubMeasurement]:
    """The dataset's subs measured since its latest master (deleted ones aside) was created; all of them when
    it has none."""
    last = (
        Master.objects.filter(dataset=ds).exclude(state=MasterState.DELETED).order_by("-created_at").first()
    )
    since = last.created_at if last else None
    subs = SubMeasurement.objects.filter(frame__dataset=ds, state=MeasureState.DONE)
    if since is not None:
        subs = subs.filter(measured_at__gt=since)
    return list(subs.select_related("frame", "frame__grade").prefetch_related("frame__verdicts"))


def _usable(measured: list[SubMeasurement]) -> list[SubMeasurement]:
    """Those whose effective verdict (a person's, else the machine grade's) is accept or down."""
    from .effective import effective

    usable = []
    for m in measured:
        try:
            g = m.frame.grade
        except MachineGrade.DoesNotExist:
            g = None
        if effective(m.frame, list(m.frame.verdicts.all()), g).verdict in ("accept", "down"):
            usable.append(m)
    return usable


def auto_stacks(now=None) -> list[int]:  # noqa: ANN001
    """Automatic stacks (004 T012, FR-011): with Settings → Stacking → Auto set, queue a default-rule master for each
    dataset that is due, and return the datasets queued. "After each session" waits until no sub has arrived for
    the quiet time; "every N new subs" counts usable subs since the last master. Fewer than 3 usable subs never
    stack, and a dataset with a master already queued or integrating waits for it."""
    from .config import processing_settings

    cfg = processing_settings()["stacking"]
    mode = cfg.get("auto", "never")
    if mode not in ("session", "every_n"):
        return []
    now = now or timezone.now()
    quiet = timedelta(hours=float(cfg.get("auto_quiet_hours") or 3))
    every = int(cfg.get("auto_every_n") or 30)
    started = []
    for ds in Dataset.objects.filter(sub_count__gt=0):
        if Master.objects.filter(dataset=ds, state__in=[MasterState.QUEUED, MasterState.RUNNING]).exists():
            continue
        new = _measured_since_last_master(ds)
        usable = _usable(new)
        if len(usable) < 3:
            continue
        times = [t for m in new if (t := m.frame.date_obs_utc or m.measured_at) is not None]
        latest = max(times) if times else None
        due = len(usable) >= every if mode == "every_n" else (latest is not None and now - latest >= quiet)
        if not due:
            continue
        try:
            made = start(ds, None, "default", None, {"auto": True})
        except ValueError:
            continue
        log.info(
            "Automatic stack for %s: master v%s (%s new usable subs)",
            ds.display_name,
            made.version,
            len(usable),
        )
        started.append(ds.pk)
    return started
