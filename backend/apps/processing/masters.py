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
    Master.objects.filter(pk=m.pk).update(step=step, progress=progress)
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
    from .models import CalibrationMatch, MatchState
    from .tasks import calibrate_batch, calibrate_file, source_path

    order: dict[int, MasterMember] = {}
    redo = work / "recal"
    todo: list = []  # (frame, match, source, where the result goes)
    links: list[tuple[Path, Path]] = []  # (result, sub_NNNNN link) for those
    for i, mm in enumerate(members, start=1):
        dest = work / f"sub_{i:05d}.fit"
        cal = Path(mm.frame.measurement.calibrated_path) if mm.frame.measurement.calibrated_path else None
        if cal is not None and cal.exists():
            os.symlink(cal, dest)
        else:
            cm = CalibrationMatch.objects.filter(frame=mm.frame, state=MatchState.MATCHED).first()
            src = source_path(mm.frame)
            if cm is None or src is None:
                mm.included, mm.reason = False, "no copy on disk" if src is None else "no longer matched"
                mm.save(update_fields=["included", "reason"])
                continue
            # into this stack's own folder: written back to the shared cache, a recalibrated sub could be pruned by
            # other workers while this stack still reads it (2026-10-13)
            out = redo / f"sub_{i:05d}.fit"
            todo.append((mm.frame, cm, src, out))
            links.append((out, dest))
        order[i] = mm
    if todo:
        _step(m, f"Calibrate ({len(todo)} subs)", 0.1)
        redo.mkdir(exist_ok=True)
        left = {f.pk for f in calibrate_batch(todo, redo)}
        for k, (frame, cm, src, out) in enumerate(todo, start=1):
            if frame.pk in left:  # one at a time, as before
                calibrate_file(frame, cm, src, redo, out)
            if k % 10 == 0:
                _step(m, f"Calibrate ({k} of {len(todo)})", 0.1 + 0.1 * k / len(todo))
        for out, dest in links:
            os.symlink(out, dest)
    return order


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

        far = max(sep(r[0], r[1]) for r in solves)
        if short and far > MOSAIC_SPREAD * short:
            return f"Mosaic: the subs' centres spread {far:.1f}° across a {short:.1f}° field"
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
        for n in notes:
            h.add_history(n[:70])


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


def _check_budget(work: Path, n: int) -> None:
    """The subs plus one registered copy each must fit the stack work budget (004 T015). A stack that can never
    fit fails with the reason; one that would fit once other stacks' working files are gone waits for them."""
    first = next(iter(sorted(work.glob("sub_*.fit*"))), None)
    if first is None:
        return
    need = first.resolve().stat().st_size * n * 2
    budget = work_budget_bytes()
    if need > budget:
        raise RuntimeError(
            f"Needs about {need / 1e9:.0f} GB of working space for {n} subs; the work budget is "
            f"{budget / 1e9:.0f} GB. Stack fewer sessions or raise the budget in Settings → Workers."
        )
    others = sum(_dir_bytes(d) for d in (Path(settings.WORK_DIR) / "integrations").glob("*") if d != work)
    if need + others > budget:
        raise Reschedule(
            600,
            f"Waiting for disk space: needs {need / 1e9:.0f} GB, other stacks use "
            f"{others / 1e9:.0f} of {budget / 1e9:.0f} GB.",
        )


def _fit_registered(eng, work: Path, n: int) -> list[str]:  # noqa: ANN001
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
    need = first.resolve().stat().st_size * n * 1.1
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


def _resumed_inputs(work: Path, ck: dict) -> dict[int, MasterMember] | None:
    """The inputs an interrupted run had linked, if every one is still there; else None (start again)."""
    order = {}
    for i, pk in (ck.get("order") or {}).items():
        mm = MasterMember.objects.select_related("frame__measurement").filter(pk=pk).first()
        if mm is None or not (work / f"sub_{int(i):05d}.fit").exists():
            return None
        order[int(i)] = mm
    return order or None


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def integrate(master_id: int) -> dict:
    from apps.engine import parse
    from apps.engine.siril import engine, heavy_memory

    from .previews import render

    m = Master.objects.select_related("dataset").get(pk=master_id)
    if m.state == MasterState.CANCELLED:
        return {"result": "cancelled"}
    Master.objects.filter(pk=m.pk).update(state=MasterState.RUNNING, started_at=timezone.now(), error=None)
    work = Path(settings.WORK_DIR) / "integrations" / f"ds{m.dataset_id}_v{m.version}"
    # 005-DR-25: a stack stopped by a redeploy resumes from what it had finished (its inputs, its registration)
    ck = _checkpoint(work, m.pk)
    if not ck["done"]:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
    keep = False
    try:
        _step(m, "Select inputs", 0.02)
        members = list(
            MasterMember.objects.filter(master=m, included=True)
            .select_related("frame__measurement")
            .order_by("pk")
        )
        cached = [
            Path(mm.frame.measurement.calibrated_path)
            for mm in members
            if mm.frame.measurement.calibrated_path
        ]
        for p in cached:  # newest in the cache, so pruning doesn't take them mid-integration
            with contextlib.suppress(FileNotFoundError):
                os.utime(p)
        _step(m, "Calibrate", 0.1)  # done on arrival; subs pruned from the cache are calibrated again here
        order = _resumed_inputs(work, ck) if "inputs" in ck["done"] else None
        if order is None:
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
            ck = {"master": m.pk, "done": []}
            order = _inputs(m, members, work)
            ck.update(done=["inputs"], order={str(i): mm.pk for i, mm in order.items()})
            _save_checkpoint(work, ck)
        check_interrupted()
        if len(order) < 2:
            raise RuntimeError("Fewer than two calibrated subs.")
        eng = engine()
        _heavy = heavy_memory()
        _heavy.__enter__()
        eng.run(f"cd {work}")
        _step(m, "Register", 0.2)
        _check_budget(work, len(order))
        mosaic = mosaic_reason([mm.frame for mm in order.values()])
        if "registered" in ck["done"] and (work / "r_sub_.seq").exists():
            notes = list(ck.get("notes", []))
            notes.append("Resumed after a restart: registration was already done.")
        elif mosaic:
            # register by plate solution onto one canvas that holds every sub (004-DR-23)
            notes = _fit_registered(eng, work, len(order))
            # full resolution: downscaled, a 10 s Seestar sub shows ~16 stars and none solve; at full size, 150–250
            # (IC 4605, 2026-10-14). Siril writes the solution into each sub's header: harmless for cached subs
            eng.run(
                "seqplatesolve sub_ -force",
                timeout=7200,
                on_line=_Live(m, "Plate solve", 0.2, 0.45, len(order)),
            )
            eng.run(
                "seqapplyreg sub_ -framing=max",
                timeout=7200,
                on_line=_Live(m, "Register", 0.45, 0.6, len(order)),
            )
            notes.append(f"{mosaic}: registered by plate solution and stacked onto one canvas.")
        elif (m.recipe.get("options") or {}).get("reference") == "most_stars":
            # the sub with the most stars is the reference; one pass keeps that choice (004 FR-004)
            best = max(order, key=lambda i: order[i].frame.measurement.stars or 0)
            notes = _fit_registered(eng, work, len(order))
            eng.run(f"setref sub_ {sorted(order).index(best) + 1}")
            eng.run("register sub_", timeout=7200, on_line=_Live(m, "Register", 0.2, 0.6, len(order)))
            notes.append(f"Reference: sub with most stars ({order[best].frame.measurement.stars:,}).")
        else:
            # two passes: Siril picks the sharpest, roundest sub as the reference (best FWHM)
            eng.run("register sub_ -2pass", timeout=7200, on_line=_Live(m, "Register", 0.2, 0.4, len(order)))
            notes = _fit_registered(eng, work, len(order))
            eng.run(
                "seqapplyreg sub_ -framing=current",
                timeout=7200,
                on_line=_Live(m, "Register", 0.4, 0.6, len(order)),
            )
        if "registered" not in ck["done"]:
            ck["done"].append("registered")
            ck["notes"] = notes
            _save_checkpoint(work, ck)
        eng.run("set32bits")
        registered = {im["filenum"] for im in parse.seq_images(work / "r_sub_.seq")}
        unmatched = []
        for i, mm in order.items():
            if i not in registered:
                mm.included, mm.reason = (
                    False,
                    ("could not plate solve" if mosaic else "could not match stars"),
                )
                mm.save(update_fields=["included", "reason"])
                unmatched.append(mm.frame_id)
        _reject_unregistered(m, unmatched, mosaic=bool(mosaic))
        _step(m, "Integrate", 0.6)
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
        out = out_dir / f"master_v{m.version}"
        cfg = m.recipe.get("options", {})
        lo, hi = (cfg.get("sigma") or [3.0, 3.0])[:2]
        weight = {"grade": "-weight=wfwhm", "snr": "-weight=noise", "equal": ""}.get(
            cfg.get("weighting", "grade"), ""
        )
        # mixed exposures (owner 2026-10-13): weight by noise (inverse
        # variance), so a 240 s sub counts for about four 60 s ones; sharpness weighting ignores exposure
        exposures = {round(mm.frame.exptime_s or 0, 3) for mm in order.values() if mm.included}
        if weight == "-weight=wfwhm" and len(exposures) > 1:
            weight = "-weight=noise"
            notes.append(
                "Mixed exposures ("
                + ", ".join(f"{e:g} s" for e in sorted(exposures))
                + "): weighted by noise, so longer subs count for more."
            )
        rej = {"winsorized": "w", "sigma": "s", "linear": "l"}.get(cfg.get("rejection", "winsorized"), "w")
        # a mosaic: the canvas holds every sub; levels match on the overlaps and edges blend
        canvas = " -maximize -overlap_norm -feather=100" if mosaic else ""
        stack = eng.run(
            f"stack r_sub_ rej {rej} {lo:g} {hi:g} -norm=addscale {weight}{canvas} -out={out} -32b".replace(
                "  ", " "
            ),
            timeout=7200,
            on_line=_Live(m, "Integrate", 0.6, 0.9, len(order)),
        )
        _step(m, "Write", 0.9)
        result = out.with_suffix(".fit")
        _provenance(result, m, notes)
        eng.run(f"load {result}")
        n, fwhm = parse.found_stars(eng.run(f"findstar -out={work / 'stars.lst'}").log)
        noise = parse.bgnoise(eng.run("bgnoise").log)
        stars = parse.star_list(work / "stars.lst")
        prev = out_dir / f"master_v{m.version}.jpg"
        try:
            render(result, prev, out_dir / f"master_v{m.version}_t.jpg")
        except Exception as exc:  # noqa: BLE001
            log.warning("Master preview failed: %s", exc)
        from .tasks import pixel_scale

        f0 = members[0].frame
        scale = pixel_scale(f0)
        included = MasterMember.objects.filter(master=m, included=True).select_related("frame")
        report = {
            "stars": n,
            "fwhm_px": fwhm,
            "fwhm_arcsec": fwhm * scale if fwhm and scale else None,
            "roundness": parse.roundness(stars),
            "noise": noise,
            "excluded_registration": len(order) - len(registered & set(order)),
            "stack_log": [line for line in stack.log if "stacked" in line or "rejection" in line.lower()][
                -4:
            ],
            "notes": notes,
            "regional": _regional(result, stars),
        }
        with transaction.atomic():
            n_new = included.count()
            for old in Master.objects.filter(
                dataset=m.dataset, state__in=[MasterState.CURRENT, MasterState.STALE]
            ):
                diff = n_new - old.sub_count
                why = (
                    f" ({diff} more sub{'s' if diff != 1 else ''})"
                    if diff > 0
                    else (f" ({-diff} fewer sub{'s' if diff != -1 else ''})" if diff < 0 else "")
                )
                Master.objects.filter(pk=old.pk).update(
                    state=MasterState.SUPERSEDED, state_reason=f"Replaced by v{m.version}{why}."
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
        reason = Master.objects.filter(pk=m.pk).values_list("state_reason", flat=True).first() or "Cancelled."
        Master.objects.filter(pk=m.pk).update(
            state=MasterState.CANCELLED, state_reason=reason, finished_at=timezone.now()
        )
        emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": "cancelled"})
        raise
    except Exception as exc:
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
    from .solving import solve_master
    from .tasks import master_view

    enqueue(solve_master, m.pk, dedupe_key=f"solve-master:{m.pk}")
    enqueue(master_view, m.pk, dedupe_key=f"master-view:{m.pk}")
    from .config import processing_settings

    post = processing_settings()["post"]
    # spec 010: the finishing chain, when switched on (globally, or for this dataset when stacking)
    if (m.report or {}).get("post_override", {}).get("enabled", post.get("enabled")):
        from .postprocess import postprocess_master

        enqueue(postprocess_master, m.pk, (m.report or {}).get("post_override"), dedupe_key=f"post:{m.pk}")
    return {"master": m.pk, "subs": len(registered)}


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


def auto_stacks(now=None) -> list[int]:  # noqa: ANN001
    """Automatic stacks (004 T012, FR-011): with Settings → Stacking → Auto set, queue a default-rule master for each
    dataset that is due, and return the datasets queued. "After each session" waits until no sub has arrived for
    the quiet time; "every N new subs" counts usable subs since the last master. Fewer than 3 usable subs never
    stack, and a dataset with a master already queued or integrating waits for it."""
    from .config import processing_settings
    from .effective import effective

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
        last = (
            Master.objects.filter(dataset=ds)
            .exclude(state=MasterState.DELETED)
            .order_by("-created_at")
            .first()
        )
        since = last.created_at if last else None
        subs = SubMeasurement.objects.filter(frame__dataset=ds, state=MeasureState.DONE)
        if since is not None:
            subs = subs.filter(measured_at__gt=since)
        new = list(subs.select_related("frame", "frame__grade").prefetch_related("frame__verdicts"))
        usable = []
        for m in new:
            try:
                g = m.frame.grade
            except MachineGrade.DoesNotExist:
                g = None
            if effective(m.frame, list(m.frame.verdicts.all()), g).verdict in ("accept", "down"):
                usable.append(m)
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
