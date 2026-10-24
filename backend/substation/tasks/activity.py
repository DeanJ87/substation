"""Activity (spec 005; v2 design A1): what every worker is doing, what is waiting and why, recent results,
host readouts, and the controls (pause, retry, cancel, move to front, dismiss). No `from __future__ import
annotations` here: see substation.api."""

import shutil
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import psutil
from django.conf import settings
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone

from substation.api import ApiError, Router, Schema, admin_required

from .models import ResourceSample, Task, TaskStatus, Worker, WorkerState
from .summary import open_failures, priority_class, queue_summary

router = Router(tags=["activity"])

KIND = {
    "hash_file": "Read new file",
    "catalogue_frame": "Catalogue",
    "calibrate_measure": "Calibrate and grade",
    "rematch_lights": "Match calibration",
    "integrate": "Integrate master",
    "reresolve_library": "Re-read values",
    "reresolve_targets": "Regroup merged names",
    "apply_ignore": "Apply ignore rule",
    "build_master": "Build master",
    "qa_calibration_set": "Check calibration frames",
    "regrade_datasets": "Re-grade",
    "rerender_previews": "Redraw previews",
    "solve_light": "Solving",
    "backfill_solves": "Queue plate solves",
    "star_map": "Star map",
    "backfill_star_maps": "Queue star maps",
    "full_view": "100% view",
    "backfill_full_views": "Queue 100% views",
    "master_view": "100% view of a master",
    "palette_view": "HOO/SHO view",
    "solve_master": "Solve master",
    "backfill_master_solves": "Queue master solves",
    "combine": "Stitch or stack masters",  # jobs queued before the two had their own names (004-DR-32)
    "stitch_mosaic": "Stitch mosaic",
    "stack_together": "Stack together",
    "auto_stacks": "Automatic stacks",
    "rerender_session": "Redraw session",
    "rerender_all_sessions": "Redraw all sessions",
    "combined_view": "100% view of a mosaic or stacked master",
    "postprocess_master": "Post-process master",
    "postprocess_combined": "Post-process mosaic or stacked master",
    "check_tools": "Check finishing tools",
    "redraw_post_views": "Redraw post-processed views",
    "activate_rc_astro": "Activate RC-Astro",
    "move_collection": "Move collection files",
    "build_progression": "Progressive stacks",
}


def kind_name(name: str) -> str:
    """ "apps.processing.tasks.rerender_all_sessions" → "Redraw all sessions"; unknown kinds read as words."""
    short = name.rsplit(".", 1)[-1]
    return KIND.get(short) or short.replace("_", " ").capitalize()


def _n(r: dict, k: str) -> str:
    return f"{r.get(k, 0):,}"


def _measured(r: dict, t: str) -> str:
    if r.get("stars") is not None:
        fwhm = f", FWHM {r['fwhm_px']:.2f} px" if r.get("fwhm_px") else ""
        return f"Measured {t}: {r['stars']:,} stars{fwhm}"
    return f"Skipped {t}: {r.get('result', 'nothing to do')}"


def _post_processed(r: dict, t: str) -> str:
    if "run" in r:
        return f"Post-processed {t}: {r.get('done', 0)} done, {r.get('skipped', 0)} skipped"
    if r.get("reason"):
        return f"Post-processing didn't start · {t}: {r['reason']}"
    return f"Post-processing {r.get('result', 'ended')} · {t}"


def _reresolved(r: dict, _t: str) -> str:
    if "frames" in r:
        return f"Re-read {_n(r, 'frames')} frames; {_n(r, 'datasets')} datasets regrouped"
    return f"Regrouped {_n(r, 'datasets')} datasets"


def _catalogued(r: dict, t: str) -> str:
    kind = f" as {str(r['frame_type']).replace('_', ' ')}" if r.get("frame_type") else ""
    return f"Catalogued {t}{kind}"


# job kind → its result as a sentence, given the job's return value and what it worked on
_OUTCOMES: dict[str, Callable[[dict, str], str]] = {
    "calibrate_measure": _measured,
    "integrate": lambda r, t: (
        f"Stacked {_n(r, 'subs')} subs · {t}" if "subs" in r else f"Stack {r.get('result', 'ended')} · {t}"
    ),
    "postprocess_master": _post_processed,
    "postprocess_combined": _post_processed,
    "build_master": lambda r, t: (
        f"Master blocked · {t}"
        if r.get("result") == "blocked"
        else f"Built master from {_n(r, 'frames')} frames · {t}"
    ),
    "rematch_lights": lambda r, _t: (
        f"Matched {_n(r, 'lights')} lights to calibration; {_n(r, 'queued')} queued to measure"
    ),
    "regrade_datasets": lambda r, _t: f"Re-graded {_n(r, 'subs')} subs in {_n(r, 'datasets')} datasets",
    "solve_light": lambda r, t: f"Solved {t}" if r.get("result") == "solved" else f"Couldn't solve {t}",
    "rerender_previews": lambda r, _t: f"Redrew {_n(r, 'previews')} previews",
    "reresolve_library": _reresolved,
    "reresolve_targets": _reresolved,
    "hash_file": lambda r, t: f"{'New' if r.get('result') == 'new' else 'Known'} file · {t}",
    "catalogue_frame": _catalogued,
    "move_collection": lambda r, t: (
        f"Moved {_n(r, 'files')} files · {t}"
        + (f"; {_n(r, 'problems')} left where they were" if r.get("problems") else "")
        if r.get("result") == "done"
        else f"Move {r.get('result', 'ended')} · {t}" + (f": {r['reason']}" if r.get("reason") else "")
    ),
}


def outcome(short: str, rv: object, target: str) -> str:
    """A finished job as a sentence (005-DR-05): what it did, not what it was called."""
    r = rv if isinstance(rv, dict) else {}
    if short in _OUTCOMES:
        return _OUTCOMES[short](r, target)
    kind = KIND.get(short, short.replace("_", " ").capitalize())
    return f"{kind} · {target}" if target else kind


def _object_label(ds) -> str:  # noqa: ANN001
    """ "Soul Nebula · Askar 71F + ATR2600M · SII": what's being worked on first, then the rig and filter. The
    collection's common name ("IC 1848 - Soul Nebula" → "Soul Nebula") when it has one, else the dataset's target
    (owner 2026-10-13: a stack listed only as "Master v1 · Askar 71F + ATR2600M · SII" said nothing of what)."""
    from apps.catalogue.services.library import label

    if ds is None:
        return ""
    col = ds.collection.name if ds.collection_id and ds.collection else ""
    name = col.split(" - ", 1)[1] if " - " in col else (col or ds.target or "")
    return " · ".join(p for p in (name, label(ds)) if p)


def _move_target(move_id: int) -> str:
    """ "Archive · M 31 · active → archive" (spec 013)."""
    from apps.catalogue.models import CollectionMove

    m = CollectionMove.objects.select_related("collection", "from_library", "to_library").get(pk=move_id)
    return f"{m.get_direction_display()} · {m.collection.name} · {m.from_library.name} → {m.to_library.name}"


def _combined_post_target(args: list) -> tuple[str, int | None, dict]:
    from apps.processing.models import CombinedMaster
    from apps.processing.postprocess import post_name

    cm = CombinedMaster.objects.select_related("collection").get(pk=args[0])
    return post_name(cm), None, {"combined_id": cm.pk, "collection_id": cm.collection_id}


# job kinds whose target comes straight from their arguments
_BY_ARGS: dict[str, Callable[[list], tuple[str, int | None, dict]]] = {
    "move_collection": lambda args: (_move_target(int(args[0])), None, {}),
    "postprocess_combined": _combined_post_target,
}


def _target(t: Task) -> tuple[str, int | None, dict]:
    """(target text, dataset id, extra) for a task, from its arguments."""
    short = t.name.rsplit(".", 1)[-1]
    args = t.args or []
    try:
        if short == "hash_file":
            return str(args[1]), None, {}
        if short == "catalogue_frame":
            return str(args[2]), None, {}
        if short in ("calibrate_measure", "solve_light"):
            from apps.catalogue.models import Frame

            f = (
                Frame.objects.select_related("dataset__rig", "dataset__collection")
                .prefetch_related("copies")
                .get(pk=args[0])
            )
            c = next(iter(f.copies.all()), None)
            name = c.rel_path.rsplit("/", 1)[-1] if c else f.sha256[:12]
            return (f"{_object_label(f.dataset)} · {name}" if f.dataset else name), f.dataset_id, {}
        if short == "integrate":
            from django.utils import timezone as _tz

            from apps.processing.masters import RULES, STEPS
            from apps.processing.models import Master

            m = Master.objects.select_related("dataset__rig", "dataset__collection", "created_by").get(
                pk=args[0]
            )
            when = _tz.localtime(m.created_at).strftime("%-d %b %H:%M")
            who = (
                f"queued by {m.created_by.get_username()} {when}"
                if m.created_by
                else f"started automatically {when}"
            )
            why = f"{who} · {RULES.get((m.recipe or {}).get('rule', 'default'), 'usable subs').lower()}"
            return (
                f"{_object_label(m.dataset)} · v{m.version}",
                m.dataset_id,
                {
                    "steps": STEPS,
                    "step": m.step,
                    "subs": m.sub_count,
                    "sessions": m.session_count,
                    "master_id": m.pk,
                    "why": why,  # who or what started it, and with which subs (owner 2026-10-13)
                },
            )
        if short in _BY_ARGS:
            return _BY_ARGS[short](args)
        if short == "build_progression":
            from apps.finished.models import FinishedProject

            fp = FinishedProject.objects.get(pk=args[0])
            return f"{fp.subject} · {fp.name}", None, {}
        if short == "postprocess_master":
            from apps.processing.models import Master

            m = Master.objects.select_related("dataset__rig", "dataset__collection").get(pk=args[0])
            return f"{_object_label(m.dataset)} · v{m.version}", m.dataset_id, {"master_id": m.pk}
        if short == "build_master":
            # "Flat OIII · 28 Sep 2026 · ATR2600M · 50 frames" (owner 2026-10-11: build jobs had no target)
            from apps.processing.models import BuiltMaster

            bm = BuiltMaster.objects.select_related("calibration_set__night").get(pk=args[0])
            cs = bm.calibration_set
            kind = {"dark_flat": "Dark flat"}.get(cs.type, cs.type.capitalize())
            what = (
                f"{kind} {cs.filter_norm}"
                if cs.type == "flat" and cs.filter_norm
                else f"{kind} {cs.exptime_s:g} s"
                + (f" {cs.set_temp_c:g} °C" if cs.set_temp_c is not None else "")
            )
            when = (cs.night.date if cs.night else cs.session_start_utc.date()).strftime("%-d %b %Y")
            return f"{what} · {when} · {cs.camera or 'unknown camera'} · {cs.frame_count} frames", None, {}
    except Exception:  # noqa: BLE001 (the console must never fail on one odd task)
        pass
    return "", None, {}


class JobOut(Schema):
    id: str
    kind: str
    name: str
    target: str
    dataset_id: int | None
    priority_class: str
    status: str
    worker: str | None
    progress: float | None
    note: str
    attempts: int
    max_attempts: int
    enqueued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    seconds: float | None
    wait_reason: str | None
    error: str | None
    log: list[str]
    extra: dict
    outcome: str = ""
    recent_log: list[list[str]] = []
    link: str | None = None  # where to see what the job made or worked on (owner 2026-10-10)


# Plain-English causes for failures people actually hit (005 T012, voice guide): pattern → sentence.
_CAUSES = [
    ("Read-only file system", "Output folder is read-only. Make the work and masters folders writable."),
    ("No space left on device", "Disk full. Free space on the work drive, then retry."),
    ("EngineDied", "Siril crashed, probably out of memory. Retry, or lower its memory share in Settings."),
    ("stopped responding", "Worker stopped responding (restarted or out of memory)."),
    ("database is locked", "Database busy. Retry."),
    ("Permission denied", "Permission denied. Check folder permissions."),
]


def _error_line(text: str | None) -> tuple[str | None, list[str]]:
    if not text:
        return None, []
    from .worker import ENGINE_MARK

    trace, _, engine = text.partition(ENGINE_MARK)
    lines = [ln for ln in trace.strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else trace
    msg = (
        last.split(": ", 1)[1]
        if ": " in last and last.split(": ", 1)[0].replace(".", "").replace("_", "").isalnum()
        else last
    )
    cause = next((why for pat, why in _CAUSES if pat in text), None)
    if cause:
        msg = f"{cause} ({msg.strip()})"
    log = lines[-8:]
    if engine:
        log += ["", "Siril output:", *[ln for ln in engine.splitlines() if ln.strip()]]
    return msg.strip(), log


def _link(short: str, args: list, ds: int | None) -> str | None:
    """A page for the job's result: the sub, the dataset's masters, the calibration set, the collection."""
    try:
        if short in ("calibrate_measure", "solve_light", "star_map", "regrade_one") and args:
            return f"/subs/{args[0]}"
        if short in ("integrate", "postprocess_master") and ds:
            return f"/datasets/{ds}?tab=masters"
        if short == "build_master" and args:
            from apps.processing.models import BuiltMaster

            set_id = (
                BuiltMaster.objects.filter(pk=args[0]).values_list("calibration_set_id", flat=True).first()
            )
            return f"/calibration/sets/{set_id}" if set_id else "/calibration"
        if short in ("combine", "stitch_mosaic", "stack_together") and args:
            return f"/collections/{args[0]}?tab=masters"
        if short == "postprocess_combined" and args:
            from apps.processing.models import CombinedMaster

            col = CombinedMaster.objects.filter(pk=args[0]).values_list("collection_id", flat=True).first()
            return f"/collections/{col}?tab=masters" if col else None
        if short == "regrade_datasets" and args and args[0]:
            return f"/datasets/{args[0][0]}?tab=quality" if len(args[0]) == 1 else "/"
        if short in ("rematch_lights", "qa_calibration_set"):
            return "/calibration"
        if short in (
            "backfill_solves",
            "backfill_star_maps",
            "hash_file",
            "catalogue_frame",
            "reresolve_library",
            "reresolve_targets",
            "apply_ignore",
        ):
            return None
    except Exception:  # noqa: BLE001
        return None
    return f"/datasets/{ds}" if ds else None


def job_out(t: Task, paused: bool = False, heavy_full: bool = False) -> JobOut:
    short = t.name.rsplit(".", 1)[-1]
    target, ds, extra = _target(t)
    wait = None
    if t.status == TaskStatus.READY:
        if paused and t.queue != "ingest":
            wait = "Paused"
        elif t.run_after and t.run_after > timezone.now():
            wait = (
                f"Retrying at {timezone.localtime(t.run_after):%H:%M}"
                if t.attempts
                else f"Scheduled for {timezone.localtime(t.run_after):%H:%M}"
            )
        elif t.slot == "siril_heavy" and heavy_full:
            wait = "Waiting for a stacking slot"
        else:
            wait = "Waiting for a free worker"
    err, log = (
        _error_line(t.error)
        if t.status in (TaskStatus.FAILED,) or (t.error and t.status == TaskStatus.READY)
        else (None, [])
    )
    secs = None
    if t.started_at:
        secs = ((t.finished_at or timezone.now()) - t.started_at).total_seconds()
    name = KIND.get(short, short.replace("_", " ").capitalize())
    if short == "integrate" and extra.get("master_id"):
        name = "Integrate master"
    return JobOut(
        id=str(t.pk),
        kind=short,
        name=name,
        target=target,
        dataset_id=ds,
        priority_class=priority_class(t.priority),
        status=t.status,
        worker=t.worker_id,
        progress=t.progress,
        note=t.progress_note or "",
        attempts=t.attempts,
        max_attempts=t.max_attempts,
        enqueued_at=t.enqueued_at,
        started_at=t.started_at,
        finished_at=t.finished_at,
        seconds=secs,
        wait_reason=wait,
        error=err,
        log=log,
        extra=extra,
        outcome=outcome(short, t.return_value, target) if t.status == TaskStatus.SUCCEEDED else "",
        recent_log=(t.log or [])[-3:] if t.status == TaskStatus.RUNNING else [],
        link=_link(short, t.args or [], ds),
    )


class WorkerOut(Schema):
    id: str
    host: str
    kind: str
    state: str
    job: JobOut | None
    uptime_s: float
    cpu_pct: float | None
    rss_bytes: int | None
    engine_cpu_pct: float | None
    engine_rss_bytes: int | None
    history: list[list[float]]  # [seconds ago, cpu %, rss MB, engine cpu %]
    verb: str = "Idle"  # what it's doing, in a word or two (005 T009)
    engine_command: str | None = None
    engine_label: str = (
        "Siril"  # the tool engine_* measures: Siril on the NAS, RC-Astro or GraXpert on a helper
    )


def _engine_label(command: str | None) -> str:
    c = (command or "").lower()
    return "RC-Astro" if "rc-astro" in c else "GraXpert" if "graxpert" in c else "Tool"


class ActivityOut(Schema):
    paused: bool
    readouts: dict
    summary: dict
    running: list[JobOut]
    workers: list[WorkerOut]
    queue: list[JobOut]
    queue_by_kind: dict[str, int]
    recent: list[JobOut]
    failed: list[JobOut]


_io = {"t": 0.0, "write": 0}


def disk_note(path) -> str | None:  # noqa: ANN001
    """Docker Desktop on a Mac reports the Mac's system disk for folders bind-mounted from an external drive, so
    the free figure can be far from the drive's real free space (005 T014). Say so rather than mislead."""
    try:
        mounts = [ln.split() for ln in open("/proc/mounts", encoding="utf-8")]  # noqa: SIM115
    except OSError:
        return None
    best = max(
        (m for m in mounts if len(m) > 2 and str(path).startswith(m[1])),
        key=lambda m: len(m[1]),
        default=None,
    )
    if best and best[2] in ("fakeowner", "grpcfuse", "virtiofs", "fuse.grpcfuse"):
        return "Mac system disk, as Docker Desktop reports it."
    return None


def _disk_write_rate() -> float | None:
    try:
        c = psutil.disk_io_counters()
    except Exception:  # noqa: BLE001
        return None
    if c is None:
        return None
    now = time.monotonic()
    rate = None
    if _io["t"]:
        rate = max(0.0, (c.write_bytes - _io["write"]) / max(0.1, now - _io["t"]))
    _io["t"], _io["write"] = now, c.write_bytes
    return rate


def _intake(libs) -> str:  # noqa: ANN001
    """Watching, Not watching (no live watcher lease) or Folder unreachable (005-DR-06)."""
    from apps.ingest.watcher import LEASE

    from .models import Lease

    if not Lease.objects.filter(name=LEASE, expires_at__gt=timezone.now()).exists():
        return "Not watching"
    live = libs.filter(enabled=True)  # a switched-off folder isn't being watched, so it can't be unreachable
    if live.filter(status="unreachable").exists():
        return "Folder unreachable"
    if live.filter(status="scanning").exists():
        return "Scanning"
    return "Watching"


VERBS = {
    "calibrate_measure": "Calibrating",
    "solve_light": "Solving",
    "hash_file": "Reading",
    "catalogue_frame": "Cataloguing",
    "build_master": "Building a master",
    "rematch_lights": "Matching",
    "regrade_datasets": "Grading",
    "rerender_previews": "Drawing previews",
    "backfill_solves": "Queueing solves",
    "star_map": "Finding stars",
    "full_view": "Drawing at 100%",
    "combine": "Stitching or stacking",
    "stitch_mosaic": "Stitching a mosaic",
    "stack_together": "Stacking together",
    "postprocess_master": "Post-processing",
    "postprocess_combined": "Post-processing",
}
STEP_VERBS = {
    "Register": "Registering",
    "Normalise": "Normalising",
    "Integrate": "Integrating",
    "Write": "Writing",
    "Calibrate": "Calibrating",
    "Select inputs": "Preparing",
}


def _verb(w: Worker) -> str:
    t = w.current_task if w.current_task and w.current_task.status == TaskStatus.RUNNING else None
    if t is None:
        return "Idle" if w.state != WorkerState.STOPPED else "Stopped"
    short = t.name.rsplit(".", 1)[-1]
    if short == "integrate":
        note = t.progress_note or ""
        return next((v for k, v in STEP_VERBS.items() if f": {k}" in note), "Integrating")
    return VERBS.get(short, KIND.get(short, short.replace("_", " ").capitalize()))


@router.get("", response=ActivityOut)
def activity(request):
    from apps.finished.progression import reconcile_progressions
    from apps.processing.masters import reconcile_states

    reconcile_states()
    reconcile_progressions()
    from apps.catalogue.models import Copy
    from apps.libraries.models import InstallationSettings, Library

    s = InstallationSettings.load()
    now = timezone.now()
    heavy_running = Task.objects.filter(status=TaskStatus.RUNNING, slot="siril_heavy").count()
    heavy_full = heavy_running >= (s.siril_heavy_slots or 1)
    running = [job_out(t) for t in Task.objects.filter(status=TaskStatus.RUNNING).order_by("started_at")]
    ready = Task.objects.filter(status=TaskStatus.READY).order_by("-priority", "enqueued_at")
    queue = [job_out(t, s.queue_paused, heavy_full) for t in ready[:40]]
    by_kind: dict[str, int] = {}
    for n, c in ready.values_list("name").annotate(c=Count("id")):
        by_kind[kind_name(n)] = by_kind.get(kind_name(n), 0) + c
    finished = Task.objects.filter(
        status__in=[TaskStatus.SUCCEEDED, TaskStatus.FAILED], finished_at__isnull=False
    )
    failed = [job_out(t) for t in open_failures()[:20]]
    recent = [job_out(t) for t in finished.filter(status=TaskStatus.SUCCEEDED).order_by("-finished_at")[:25]]
    alive = Worker.objects.filter(heartbeat_at__gte=now - timedelta(seconds=30)).exclude(
        state=WorkerState.STOPPED
    )
    workers = []
    for w in alive.select_related("current_task").order_by("id"):
        samples = list(
            ResourceSample.objects.filter(worker=w, at__gte=now - timedelta(minutes=15))
            .order_by("at")
            .values_list("at", "cpu_pct", "rss_bytes", "engine_cpu_pct", "engine_rss_bytes")
        )
        last = samples[-1] if samples else None
        step = max(1, len(samples) // 90)
        helper = w.id.startswith("helper:")
        workers.append(
            WorkerOut(
                id=w.id,
                host=w.id.removeprefix("helper:") if helper else w.id.split("-worker")[0],
                kind="helper" if helper else w.kind,
                state=w.state,
                job=job_out(w.current_task)
                if w.current_task and w.current_task.status == TaskStatus.RUNNING
                else None,
                uptime_s=(now - w.started_at).total_seconds(),
                cpu_pct=last[1] if last else None,
                rss_bytes=last[2] if last else None,
                engine_cpu_pct=last[3] if last else None,
                engine_rss_bytes=last[4] if last else None,
                history=[
                    [round((now - a).total_seconds()), round(c, 1), round(r / 2**20), round(e, 1)]
                    for a, c, r, e, _ in samples[::step]
                ],
                verb=_verb(w),
                engine_command=w.engine_command,
                engine_label=_engine_label(w.engine_command) if helper else "Siril",
            )
        )
    vm = psutil.virtual_memory()
    where = next((d for d in (settings.WORK_DIR, settings.STACKS_DIR) if d.exists()), settings.STATION_ROOT)
    try:
        du = shutil.disk_usage(where)
        disk: dict[str, int | None] = {"free": du.free, "total": du.total}
    except OSError:
        disk = {"free": None, "total": None}
    libs = Library.objects.filter(enabled=True)
    last_file = Copy.objects.order_by("-first_seen_at").values_list("first_seen_at", flat=True).first()
    readouts = {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "threads": psutil.cpu_count() or 0,
        "workers": len(workers),
        "mem_used": vm.total - vm.available,
        "mem_total": vm.total,
        "disk_write_bps": _disk_write_rate(),
        "disk_free": disk["free"],
        "disk_total": disk["total"],
        "disk_note": disk_note(where),
        "folders": libs.count(),
        "last_file_at": last_file,
        "heavy_slots": s.siril_heavy_slots,
        "heavy_running": heavy_running,
        "worker_count": s.worker_count,
        "intake": _intake(libs),
        "work_used": s.work_used or {},
        "work_budget_bytes": (s.work_budget_gb or settings.STACK_WORK_BUDGET_GB) * 1e9,
    }
    return ActivityOut(
        paused=s.queue_paused,
        readouts=readouts,
        summary=queue_summary(),
        running=running,
        workers=workers,
        queue=queue,
        queue_by_kind=by_kind,
        recent=recent,
        failed=failed,
    )


class PauseIn(Schema):
    paused: bool


@router.post("/pause", response=dict[str, bool])
@admin_required
def pause(request, body: PauseIn):
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    s.queue_paused = body.paused
    s.save(update_fields=["queue_paused"])
    return {"paused": s.queue_paused}


@router.post("/jobs/{id}/retry", response=JobOut)
@admin_required
def retry(request, id: str):  # noqa: A002
    t = get_object_or_404(Task, pk=id)
    if t.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise ApiError(409, "not_failed", "Only failed or cancelled jobs can be retried.")
    _requeue(t)
    return job_out(t)


def _requeue(t: Task) -> None:
    t.status, t.attempts, t.run_after, t.finished_at, t.worker = (
        TaskStatus.READY,
        0,
        timezone.now(),
        None,
        None,
    )
    t.progress_note = ""
    t.save()


@router.post("/jobs/{id}/cancel", response=JobOut)
@admin_required
def cancel(request, id: str):  # noqa: A002
    t = get_object_or_404(Task, pk=id)
    if t.status == TaskStatus.RUNNING:  # stopped at its next check; it then shows as cancelled
        t.cancel_requested = True
        t.progress_note = f"Cancelling (asked by {request.user.get_username()})"
        t.save(update_fields=["cancel_requested", "progress_note"])
        return job_out(t)
    if t.status != TaskStatus.READY:
        raise ApiError(409, "not_waiting", "Only waiting or running jobs can be cancelled.")
    t.status, t.finished_at = TaskStatus.CANCELLED, timezone.now()
    t.save(update_fields=["status", "finished_at"])
    from apps.finished.progression import reconcile_progressions
    from apps.processing.masters import reconcile_states

    reconcile_states()
    reconcile_progressions()
    return job_out(t)


@router.get("/queue", response=list[JobOut])
def queue_page(request, offset: int = 0, limit: int = 50, kind: str | None = None):
    """The waiting jobs a page at a time, in the order they'll run (owner 2026-10-11: scroll the whole queue);
    `kind` keeps one kind of job, named as the queue's chips name them ("Calibrate and grade")."""
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    heavy_full = Task.objects.filter(status=TaskStatus.RUNNING, slot="siril_heavy").count() >= (
        s.siril_heavy_slots or 1
    )
    ready = Task.objects.filter(status=TaskStatus.READY).order_by("-priority", "enqueued_at")
    if kind:
        names = {n for n in ready.values_list("name", flat=True).distinct() if kind_name(n) == kind}
        ready = ready.filter(name__in=names)
    return [job_out(t, s.queue_paused, heavy_full) for t in ready[offset : offset + min(limit, 200)]]


@router.get("/recent", response=list[JobOut])
def recent_page(request, offset: int = 0, limit: int = 50):
    """Finished jobs, newest first, a page at a time."""
    done = Task.objects.filter(status=TaskStatus.SUCCEEDED, finished_at__isnull=False).order_by(
        "-finished_at"
    )
    return [job_out(t) for t in done[offset : offset + min(limit, 200)]]


@router.post("/jobs/{id}/bump", response=JobOut)
@admin_required
def bump(request, id: str):  # noqa: A002
    t = get_object_or_404(Task, pk=id)
    if t.status != TaskStatus.READY:
        raise ApiError(409, "not_waiting", "Only waiting jobs can be moved.")
    top = (
        Task.objects.filter(status=TaskStatus.READY)
        .order_by("-priority")
        .values_list("priority", flat=True)
        .first()
        or 0
    )
    t.priority = max(t.priority, top + 1)
    t.save(update_fields=["priority"])
    return job_out(t)


class MoveIn(Schema):
    before: str | None = None
    after: str | None = None


@router.post("/jobs/{id}/move", response=JobOut)
@admin_required
def move(request, id: str, body: MoveIn):  # noqa: A002
    """Place a waiting job just before or after another (005 T008). The queue runs by priority, then by enqueue
    time, so the job takes the other's priority and an enqueue time a moment either side of it."""
    from datetime import timedelta

    t = get_object_or_404(Task, pk=id)
    if t.status != TaskStatus.READY:
        raise ApiError(409, "not_waiting", "Only waiting jobs can be moved.")
    other_id = body.before or body.after
    if not other_id or (body.before and body.after):
        raise ApiError(422, "invalid", "Choose a job to move next to.")
    other = get_object_or_404(Task, pk=other_id, status=TaskStatus.READY)
    t.priority = other.priority
    t.enqueued_at = other.enqueued_at + timedelta(milliseconds=-1 if body.before else 1)
    t.save(update_fields=["priority", "enqueued_at"])
    return job_out(t)


@router.post("/jobs/{id}/dismiss", response=JobOut)
def dismiss(request, id: str):  # noqa: A002
    t = get_object_or_404(Task, pk=id, status=TaskStatus.FAILED)
    t.progress_note = "dismissed"
    t.save(update_fields=["progress_note"])
    return job_out(t)


# ---- many at once (spec 016 U6) --------------------------------------------------------------------------------
class JobIdsIn(Schema):
    ids: list[str]


class JobsDoneOut(Schema):
    done: int
    change_id: int | None = None  # dismissing can be undone with POST /changes/{id}/undo


def _failed(ids: list[str]):  # noqa: ANN202
    import uuid

    if len(ids) > 500:
        raise ApiError(422, "too_many", "Up to 500 jobs at a time.")
    ok = []
    for i in ids:
        try:
            ok.append(uuid.UUID(i))
        except ValueError:
            continue
    return Task.objects.filter(pk__in=ok, status=TaskStatus.FAILED)


@router.post("/bulk/jobs/retry", response=JobsDoneOut)
@admin_required
def retry_many(request, body: JobIdsIn):
    """Run these failed jobs again; ones no longer failed are left alone."""
    n = 0
    for t in _failed(body.ids):
        _requeue(t)
        n += 1
    return JobsDoneOut(done=n)


@router.post("/bulk/jobs/dismiss", response=JobsDoneOut)
def dismiss_many(request, body: JobIdsIn):
    """Take these failures off Activity's list; recorded, so undoing shows them again."""
    from apps.accounts.roles import is_viewer
    from apps.catalogue.models import Change
    from apps.catalogue.services.changes import record

    if is_viewer(request.user):
        raise ApiError(403, "read_only", "Your account can't dismiss jobs.")
    before = dict(_failed(body.ids).exclude(progress_note="dismissed").values_list("pk", "progress_note"))
    n = Task.objects.filter(pk__in=before).update(progress_note="dismissed")
    if not n:
        return JobsDoneOut(done=0)
    change = record(
        request.user,
        Change.Kind.DISMISS,
        f"Dismissed {n:,} failed job{'s' if n != 1 else ''}",
        n,
        tasks={str(pk): note for pk, note in before.items()},
    )
    return JobsDoneOut(done=n, change_id=change.pk)
