"""SubStation tasks: Django's Tasks API plus the options our SQLite backend needs (research R2).

Define tasks with `station_task` (a thin layer over `django_tasks.task`) and enqueue them with `enqueue`,
which adds a dedupe key. Inside a running task, `report_progress` updates the queue console and
`Reschedule` puts the task back without counting a failed attempt (for example "file still being written").
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from django_tasks import task as dj_task
from django_tasks.base import Task as DjTask

log = logging.getLogger("substation.tasks")

PRIORITY_LIVE = 80
PRIORITY_BULK = 40
PRIORITY_ARCHIVE = 10


@dataclass(frozen=True)
class TaskOptions:
    slot: str = "light"
    max_attempts: int = 3


_OPTIONS: dict[str, TaskOptions] = {}
_enqueue_opts: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "enqueue_opts", default=None
)
current_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_task_id", default=None)


def module_path(func: Callable[..., Any]) -> str:
    return f"{func.__module__}.{func.__qualname__}"


def station_task(
    *, priority: int = 0, queue_name: str = "default", slot: str = "light", max_attempts: int = 3
) -> Callable[[Callable[..., Any]], DjTask]:
    def wrap(func: Callable[..., Any]) -> DjTask:
        _OPTIONS[module_path(func)] = TaskOptions(slot=slot, max_attempts=max_attempts)
        return dj_task(priority=priority, queue_name=queue_name)(func)

    return wrap


def options_for(name: str) -> TaskOptions:
    return _OPTIONS.get(name, TaskOptions())


def enqueue(
    task: DjTask,
    *args: Any,
    dedupe_key: str | None = None,
    priority: int | None = None,
    run_after: datetime | None = None,
    **kwargs: Any,
):  # -> TaskResult
    """Enqueue `task`. If `dedupe_key` matches a queued or running task, that task's result is returned."""
    t = task.using(priority=priority, run_after=run_after) if (priority is not None or run_after) else task
    token = _enqueue_opts.set({"dedupe_key": dedupe_key})
    try:
        return t.enqueue(*args, **kwargs)
    finally:
        _enqueue_opts.reset(token)


def pending_enqueue_options() -> dict[str, Any]:
    return _enqueue_opts.get() or {}


class Cancelled(Exception):  # noqa: N818 (control flow)
    """Raised inside a running task when someone has asked to stop it: the task ends as cancelled, not failed."""


_cancel_checked: dict[str, float] = {}


def cancel_requested() -> bool:
    """True when the running task has been asked to stop. Cheap to call often: asks the database at most every
    2 s per task."""
    import time

    task_id = current_task_id.get()
    if task_id is None:
        return False
    now = time.monotonic()
    if now - _cancel_checked.get(task_id, 0.0) < 2.0:
        return False
    _cancel_checked[task_id] = now
    from .models import Task

    return Task.objects.filter(pk=task_id, cancel_requested=True).exists()


def check_cancelled() -> None:
    if cancel_requested():
        raise Cancelled("Cancelled while running.")


class Reschedule(Exception):  # noqa: N818 (control flow, not an error)
    """Raise inside a task to run it again later without counting a failed attempt."""

    def __init__(self, delay_s: float, note: str = "") -> None:
        super().__init__(note)
        self.run_after = timezone.now() + timedelta(seconds=delay_s)
        self.note = note


def report_progress(fraction: float | None, note: str = "") -> None:
    task_id = current_task_id.get()
    if task_id is None:
        return
    from django.db import OperationalError

    from .models import Task

    # a progress note is for the Activity page: a busy database (another container mid-write) must not fail the
    # task it describes (a 29 Sep flat build failed on one, 2026-10-12); the next note catches up
    try:
        Task.objects.filter(pk=task_id).update(progress=fraction, progress_note=note[:300])
        if note:
            _log(task_id, note)
    except OperationalError:
        log.warning("Couldn't record progress for %s (database busy); carrying on.", task_id)
    check_cancelled()


def _log(task_id: str, note: str) -> None:
    """Keep the last 20 distinct notes for the running card's log lines (005-DR-02)."""
    from django.utils import timezone

    from .models import Task

    row = Task.objects.filter(pk=task_id).values_list("log", flat=True).first()
    lines = list(row or [])
    if lines and lines[-1][1] == note[:200]:
        return
    lines = (lines + [[timezone.now().isoformat(timespec="seconds"), note[:200]]])[-20:]
    Task.objects.filter(pk=task_id).update(log=lines)
