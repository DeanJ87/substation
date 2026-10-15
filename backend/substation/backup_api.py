"""Backups in Settings (spec 014): list, back up now, download, restore. Admins only. No `from __future__ import
annotations` here: see substation.api."""

from datetime import datetime
from pathlib import Path

from django.http import FileResponse

from substation.api import ApiError, Router, Schema, admin_required
from substation.tasks import PRIORITY_LIVE, Reschedule, enqueue, station_task

router = Router(tags=["backups"])


class BackupOut(Schema):
    name: str
    size_bytes: int
    made_at: datetime


class BackupsOut(Schema):
    folder: str
    writable: bool
    backups: list[BackupOut]
    running: bool = False


class RestoreIn(Schema):
    confirm: str = ""


class BackupQueuedOut(Schema):
    queued: bool
    note: str = ""


@station_task(queue_name="default", priority=PRIORITY_LIVE, max_attempts=1)
def backup_database() -> dict:
    from apps.processing.config import processing_settings

    from .backup import make_backup, prune

    path = make_backup()
    keep = int((processing_settings().get("backup") or {}).get("keep", 14))
    return {"result": f"Backed up to {path.name}", "pruned": prune(keep)}


@station_task(queue_name="default", priority=PRIORITY_LIVE, max_attempts=1)
def restore_database(name: str) -> dict:
    """Pause new work, wait for what's running, then replace the database in one transaction; the pause is lifted
    afterwards (its own setting was replaced too)."""
    from apps.libraries.models import InstallationSettings

    from .backup import folder, restore
    from .tasks import current_task_id
    from .tasks.models import Task, TaskStatus

    s = InstallationSettings.load()
    if not s.queue_paused:
        InstallationSettings.objects.filter(pk=s.pk).update(queue_paused=True)
    me = current_task_id.get()
    others = Task.objects.filter(status=TaskStatus.RUNNING)
    if me:
        others = others.exclude(pk=me)
    if others.exists():
        raise Reschedule(20, f"Waiting for {others.count()} running job(s) before restoring.")
    try:
        out = restore(folder() / name)
    finally:
        InstallationSettings.objects.update(queue_paused=False)
    return {"result": f"Restored {name}: {out['rows']:,} rows in {out['tables']} tables"}


def _safe(name: str) -> Path:
    from .backup import PREFIX, folder

    p = folder() / Path(name).name
    if not p.name.startswith(PREFIX) or not p.name.endswith(".tar.gz") or not p.is_file():
        raise ApiError(404, "not_found", "No such backup.")
    return p


@router.get("", response=BackupsOut)
@admin_required
def backups(request):
    import os

    from .backup import folder, list_backups
    from .tasks.models import Task, TaskStatus

    f = folder()
    running = (
        Task.objects.filter(
            name__endswith="backup_database", status__in=[TaskStatus.READY, TaskStatus.RUNNING]
        ).exists()
        or Task.objects.filter(
            name__endswith="restore_database", status__in=[TaskStatus.READY, TaskStatus.RUNNING]
        ).exists()
    )
    probe = f if f.exists() else f.parent
    return BackupsOut(
        folder=str(f),
        writable=os.access(probe, os.W_OK),
        backups=[BackupOut(**b) for b in list_backups(f)],
        running=running,
    )


@router.post("", response=BackupQueuedOut)
@admin_required
def back_up_now(request):
    enqueue(backup_database, dedupe_key="backup-database")
    return BackupQueuedOut(queued=True, note="Backing up.")


@router.get("/{name}/download", response={200: None, 404: None})
@admin_required
def download(request, name: str):
    p = _safe(name)
    return FileResponse(p.open("rb"), as_attachment=True, filename=p.name)


@router.post("/{name}/restore", response=BackupQueuedOut)
@admin_required
def restore_now(request, name: str, body: RestoreIn):
    if body.confirm.strip().lower() != "restore":
        raise ApiError(
            422, "confirm", 'Type "restore" to replace everything SubStation knows with this backup.'
        )
    p = _safe(name)
    from .backup import BackupError, read_manifest

    try:
        read_manifest(p)
    except (BackupError, OSError) as exc:
        raise ApiError(422, "invalid", str(exc)) from None
    enqueue(restore_database, p.name, dedupe_key="restore-database")
    return BackupQueuedOut(
        queued=True, note="New work is paused; the restore starts once running jobs finish."
    )
