"""Post-processing helpers (spec 010, owner 2026-10-13): RC-Astro shreds the NAS's CPU, so finishing runs on a
faster machine — the owner's Mac, natively, where RC-Astro uses the GPU. A helper asks for the next master over
HTTPS, downloads it, runs GraXpert → BlurXTerminator → NoiseXTerminator, uploads each stage, and says when it's
done; SubStation then draws the previews, 100% views and measurements as for any run.

Helpers authenticate with a shared token (SUBSTATION_HELPER_TOKEN, a stack variable; never in git). No helper,
no finishing: the jobs wait, and the master says so."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.security import APIKeyHeader

from substation.api import ApiError
from substation.tasks.models import ResourceSample, Task, TaskStatus, Worker, WorkerState

HELPER_TASK = "apps.processing.postprocess.postprocess_master"
# 2026-10-24: a stitched mosaic or stacked-together master goes through the same helpers
HELPER_TASKS = {HELPER_TASK: "master", "apps.processing.postprocess.postprocess_combined": "combined"}


class HelperToken(APIKeyHeader):
    param_name = "X-Helper-Token"

    def authenticate(self, request, key):  # noqa: ANN001, ANN201
        import hmac

        token = getattr(settings, "SUBSTATION_HELPER_TOKEN", "")
        return key if token and key and hmac.compare_digest(key, token) else None


router = Router(auth=HelperToken(), tags=["helper"])


class HelperToolState(Schema):
    ready: bool
    reason: str = ""


class HelperSample(Schema):
    """CPU and memory of the helper and the tool it's running, shown in Activity like a NAS worker's."""

    cpu_pct: float
    rss_bytes: int
    tool_cpu_pct: float = 0
    tool_rss_bytes: int = 0


class HelperClaimIn(Schema):
    host: str
    tools: dict[str, HelperToolState] = {}
    version: str = ""
    sample: HelperSample | None = None


class HelperJobOut(Schema):
    task_id: str
    master_id: int  # the master's id, or the combined master's when `kind` is "combined"
    kind: str = "master"
    name: str
    master_url: str
    master_file: str  # stage uploads are stored as <master stem>_<step>.fits
    settings: dict[str, Any]


class HelperProgressIn(Schema):
    fraction: float | None = None
    note: str = ""
    sample: HelperSample | None = None
    command: str = ""  # the tool's command line while one runs, as Activity shows Siril's


class HelperProgressOut(Schema):
    cancel: bool = False


class HelperStageIn(Schema):
    step: str
    label: str
    state: str  # done, skipped, failed
    tool: str = ""
    seconds: float | None = None
    reason: str = ""
    params: dict[str, Any] = {}
    input: str = ""
    file_name: str = ""  # set when the stage was uploaded


class HelperDoneIn(Schema):
    stages: list[HelperStageIn]


def _worker(host: str) -> Worker:
    wid = f"helper:{host}"[:64]
    now = timezone.now()
    w, _ = Worker.objects.get_or_create(pk=wid, defaults={"pid": 0, "started_at": now, "heartbeat_at": now})
    Worker.objects.filter(pk=wid).update(heartbeat_at=now)
    return w


def _sample(host: str, sample: HelperSample | None) -> None:
    if sample is None:
        return
    now = timezone.now()
    wid = f"helper:{host}"[:64]
    ResourceSample.objects.create(
        worker_id=wid,
        cpu_pct=sample.cpu_pct,
        rss_bytes=sample.rss_bytes,
        engine_cpu_pct=sample.tool_cpu_pct,
        engine_rss_bytes=sample.tool_rss_bytes,
        at=now,
    )
    ResourceSample.objects.filter(worker_id=wid, at__lt=now - timedelta(hours=1)).delete()


def _seen(host: str, tools: dict, version: str) -> None:
    """Record the helper and what it can run, for Settings and the masters waiting on it."""
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    p = dict(s.processing or {})
    p["post_tools"] = {
        "checked_at": timezone.now().isoformat(),
        "host": host,
        "note": f"helper {version}".strip(),
        **{k: {"ready": v.ready, "reason": v.reason} for k, v in tools.items()},
    }
    p["helper_seen"] = {"host": host, "at": timezone.now().isoformat()}
    InstallationSettings.objects.filter(pk=s.pk).update(processing=p)


def _task(task_id: str, host: str) -> Task:
    t = get_object_or_404(Task, pk=task_id, name__in=list(HELPER_TASKS))
    if t.status != TaskStatus.RUNNING or t.worker_id != f"helper:{host}"[:64]:
        raise ApiError(409, "not_yours", "This job isn't running on this helper any more.")
    return t


def _target(t: Task):  # noqa: ANN202
    """The master or combined master a helper job works on."""
    from .postprocess import post_object

    obj = post_object(HELPER_TASKS[t.name], t.args[0])
    if obj is None:
        raise ApiError(404, "gone", "This master was deleted.")
    return obj


def _stage_dir(t: Task) -> tuple[Path, Path]:
    src = Path(_target(t).output_path)
    return src, src.parent / f"{src.stem}_post-{str(t.pk)[:8]}"


@router.post("/claim", response={200: HelperJobOut, 204: None})
def claim_job(request, body: HelperClaimIn):
    """The next master to post-process, or nothing (204). Also the helper's heartbeat while idle."""
    from substation.tasks.claim import claim

    from .config import _merge, processing_settings
    from .postprocess import failed_run, post_name, post_object, record_run, size_problem

    w = _worker(body.host)
    _seen(body.host, body.tools, body.version)
    _sample(body.host, body.sample)
    row = claim(w.pk, heavy_slots=1, only=["finish"])
    if row is None:
        Worker.objects.filter(pk=w.pk).update(state=WorkerState.IDLE, current_task=None, engine_command=None)
        return 204, None
    Worker.objects.filter(pk=w.pk).update(state=WorkerState.BUSY, current_task=row)
    kind = HELPER_TASKS.get(row.name, "master")
    m = post_object(kind, row.args[0])
    if m is None or not m.output_path or not Path(m.output_path).is_file():
        Task.objects.filter(pk=row.pk).update(
            status=TaskStatus.FAILED, finished_at=timezone.now(), error="The master's file is missing."
        )
        return 204, None
    overrides = row.args[1] if len(row.args) > 1 and isinstance(row.args[1], dict) else {}
    cfg = _merge(processing_settings()["post"], overrides)
    src = Path(m.output_path)
    # the stages come back here to be measured and drawn, so a canvas too big for this server is refused now
    problem = size_problem(src, src.parent / f"{src.stem}_post-{str(row.pk)[:8]}", cfg)
    if problem:
        record_run(m, failed_run(problem, cfg))
        Task.objects.filter(pk=row.pk).update(
            status=TaskStatus.FAILED, finished_at=timezone.now(), error=problem
        )
        Worker.objects.filter(pk=w.pk).update(state=WorkerState.IDLE, current_task=None)
        return 204, None
    return 200, HelperJobOut(
        task_id=str(row.pk),
        master_id=m.pk,
        kind=kind,
        name=post_name(m),
        master_url=f"/api/v1/helper/tasks/{row.pk}/master",
        master_file=src.name,
        settings=cfg,
    )


@router.get("/tasks/{task_id}/master", response={200: None})
def download_master(request, task_id: str, host: str):
    t = _task(task_id, host)
    src, _ = _stage_dir(t)
    return FileResponse(src.open("rb"), as_attachment=True, filename=src.name)


@router.post("/tasks/{task_id}/progress", response=HelperProgressOut)
def job_progress(request, task_id: str, host: str, body: HelperProgressIn):
    """Progress, and the heartbeat that keeps the job from being taken back."""
    from substation.tasks import _log

    t = _task(task_id, host)
    now = timezone.now()
    fields: dict[str, Any] = {"heartbeat_at": now}
    if body.note:
        fields["progress_note"] = body.note[:300]
    if body.fraction is not None:
        fields["progress"] = max(0.0, min(1.0, body.fraction))
    Task.objects.filter(pk=t.pk).update(**fields)
    Worker.objects.filter(pk=f"helper:{host}"[:64]).update(
        heartbeat_at=now, engine_command=body.command[:300] or None
    )
    _sample(host, body.sample)
    if body.note:
        _log(str(t.pk), body.note)
    return HelperProgressOut(cancel=bool(t.cancel_requested))


@router.post("/tasks/{task_id}/stage/{index}", response={204: None})
def upload_stage(
    request, task_id: str, index: int, host: str, step: str, offset: int | None = None, last: bool = True
):
    """One stage's linear FITS, streamed to disk beside the master (never held in memory).

    A proxy may cut a request off after a minute, so a big stage can come in pieces: each piece says where it
    starts (`offset`) and the final one says `last`. Sending a piece again overwrites from its offset, so a
    retried piece is harmless. Without `offset` the body is the whole file."""
    t = _task(task_id, host)
    src, out_dir = _stage_dir(t)
    target = out_dir / f"step{index}_{step}" / f"{src.stem}_{step}.fits"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    start = offset or 0
    if start and (not tmp.exists() or tmp.stat().st_size < start):
        raise ApiError(409, "gap", "A piece of this stage is missing; send it again from the start.")
    with tmp.open("r+b" if start else "wb") as fh:
        fh.seek(start)
        while chunk := request.read(8 << 20):
            fh.write(chunk)
        fh.truncate()
    if last:
        tmp.replace(target)
    return 204, None


@router.post("/tasks/{task_id}/done", response={204: None})
def job_done(request, task_id: str, host: str, body: HelperDoneIn):
    """Record the run: previews, 100% views and measurements are drawn here, as for a run on the NAS."""
    from .config import _merge, processing_settings
    from .postprocess import emit_updated, record_run, stage_views

    t = _task(task_id, host)
    src, out_dir = _stage_dir(t)
    stages = []
    for i, st in enumerate(body.stages):
        rec = st.dict()
        name = rec.pop("file_name", "")
        if rec["state"] == "done" and name:
            p = out_dir / f"step{i}_{st.step}" / name
            if p.is_file():
                rec["path"] = str(p)
            else:
                rec["state"], rec["reason"] = (
                    "failed",
                    "The helper said it uploaded this stage, but it isn't here.",
                )
        stages.append(rec)
    run_stats: dict = {}
    stage_views(src, stages, run_stats)
    m = _target(t)
    # the settings the helper was given: Settings → Processing with this run's own choice of steps (010-DR-29)
    overrides = t.args[1] if len(t.args) > 1 and isinstance(t.args[1], dict) else {}
    cfg = _merge(processing_settings()["post"], overrides)
    run = {
        "started_at": (t.started_at or timezone.now()).isoformat(),
        "finished_at": timezone.now().isoformat(),
        "stages": stages,
        "settings": cfg,
        "helper": host,
        **run_stats,
    }
    if cfg.get("chosen_steps") is not None:
        run["chosen"] = cfg["chosen_steps"]
    record_run(m, run)
    done = sum(1 for s in stages if s.get("state") == "done")
    Task.objects.filter(pk=t.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        progress=1.0,
        return_value={"run": run["run"], "done": done, "skipped": len(stages) - done, "helper": host},
    )
    Worker.objects.filter(pk=f"helper:{host}"[:64]).update(
        state=WorkerState.IDLE, current_task=None, engine_command=None
    )
    emit_updated(m)
    return 204, None


class HelperFailIn(Schema):
    reason: str


@router.post("/tasks/{task_id}/fail", response={204: None})
def job_failed(request, task_id: str, host: str, body: HelperFailIn):
    """A run that went wrong. While it has attempts left it goes back in the queue (a dropped connection or a
    helper restart shouldn't cost the master its post-processing); after that it fails with the helper's reason."""
    from substation.tasks.worker import backoff

    t = _task(task_id, host)
    reason = f"Helper {host}: {body.reason}"[:2000]
    if t.attempts < t.max_attempts:
        Task.objects.filter(pk=t.pk).update(
            status=TaskStatus.READY, worker=None, run_after=timezone.now() + backoff(t.attempts), error=reason
        )
    else:
        Task.objects.filter(pk=t.pk).update(
            status=TaskStatus.FAILED, finished_at=timezone.now(), error=reason
        )
    Worker.objects.filter(pk=f"helper:{host}"[:64]).update(
        state=WorkerState.IDLE, current_task=None, engine_command=None
    )
    return 204, None


@router.post("/ping", response={204: None})
def ping(request, body: HelperClaimIn):
    """Say hello without taking a job: the helper's tools show in Settings."""
    _worker(body.host)
    _seen(body.host, body.tools, body.version)
    _sample(body.host, body.sample)
    return 204, None
