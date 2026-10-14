"""SubStation's task backend for the Django Tasks API: tasks are rows in the database (research R2)."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from django_tasks.backends.base import BaseTaskBackend
from django_tasks.base import Task as DjTask
from django_tasks.base import TaskError, TaskResult, TaskResultStatus
from django_tasks.exceptions import TaskResultDoesNotExist
from django_tasks.utils import normalize_json

from . import module_path, options_for, pending_enqueue_options
from .models import Task, TaskStatus

_STATUS = {
    TaskStatus.READY: TaskResultStatus.READY,
    TaskStatus.RUNNING: TaskResultStatus.RUNNING,
    TaskStatus.SUCCEEDED: TaskResultStatus.SUCCESSFUL,
    TaskStatus.FAILED: TaskResultStatus.FAILED,
    TaskStatus.CANCELLED: TaskResultStatus.FAILED,
}


def load_task(name: str) -> DjTask:
    obj = import_string(name)
    if not isinstance(obj, DjTask):
        raise TypeError(f"{name} is not a task")
    return obj


def to_result(row: Task, task: DjTask | None = None) -> TaskResult:
    task = task or load_task(row.name)
    errors = [TaskError(exception_class_path="builtins.Exception", traceback=row.error)] if row.error else []
    result: TaskResult = TaskResult(
        task=task,
        id=str(row.id),
        status=_STATUS[TaskStatus(row.status)],
        enqueued_at=row.enqueued_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        last_attempted_at=row.started_at,
        args=row.args,
        kwargs=row.kwargs,
        backend="default",
        errors=errors,
        worker_ids=[row.worker_id] if row.worker_id else [],
    )
    object.__setattr__(result, "_return_value", row.return_value)
    return result


class SubStationTaskBackend(BaseTaskBackend):
    supports_defer = True
    supports_get_result = True
    supports_priority = True

    def enqueue(self, task: DjTask, args: Any, kwargs: Any) -> TaskResult:
        self.validate_task(task)
        name = module_path(task.func)
        opts = options_for(name)
        dedupe_key = pending_enqueue_options().get("dedupe_key")
        now = timezone.now()
        fields = {
            "name": name,
            "args": normalize_json(list(args)),
            "kwargs": normalize_json(dict(kwargs)),
            "queue": task.queue_name,
            "priority": task.priority,
            "slot": opts.slot,
            "max_attempts": opts.max_attempts,
            "run_after": task.run_after or now,
            "enqueued_at": now,
            "dedupe_key": dedupe_key,
        }
        if dedupe_key:
            existing = Task.objects.filter(
                dedupe_key=dedupe_key, status__in=[TaskStatus.READY, TaskStatus.RUNNING]
            ).first()
            if existing and existing.status == TaskStatus.RUNNING and pending_enqueue_options().get("fresh"):
                # it may have read the state before this change: it keeps running, without the key, and a new
                # run waits behind it
                Task.objects.filter(pk=existing.pk).update(dedupe_key=None)
                existing = None
            if existing:
                return to_result(existing, task)
            # A finished task with the same key frees the key for a new run.
            Task.objects.filter(dedupe_key=dedupe_key).exclude(
                status__in=[TaskStatus.READY, TaskStatus.RUNNING]
            ).update(dedupe_key=None)
        try:
            with transaction.atomic():
                row = Task.objects.create(**fields)
        except IntegrityError:
            row = Task.objects.get(dedupe_key=dedupe_key)
        return to_result(row, task)

    def get_result(self, result_id: str) -> TaskResult:
        try:
            row = Task.objects.get(pk=result_id)
        except (Task.DoesNotExist, ValueError) as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        return to_result(row)
