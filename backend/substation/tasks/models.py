"""Queue tables (data-model.md: Task, Worker, ResourceSample)."""

from __future__ import annotations

import uuid

from django.db import models


class TaskStatus(models.TextChoices):
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Slot(models.TextChoices):
    LIGHT = "light"
    SIRIL_HEAVY = "siril_heavy"


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="dotted path of the task function")
    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)
    queue = models.CharField(max_length=50, default="default")
    priority = models.SmallIntegerField(default=0, help_text="-100..100, higher runs first")
    slot = models.CharField(max_length=20, choices=Slot.choices, default=Slot.LIGHT)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.READY)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    run_after = models.DateTimeField()
    progress = models.FloatField(null=True, blank=True, help_text="0-1")
    progress_note = models.CharField(max_length=300, blank=True, default="")
    worker = models.ForeignKey(
        "Worker", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    enqueued_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    cancel_requested = models.BooleanField(
        default=False, help_text="stop this running task at its next check"
    )
    log = models.JSONField(null=True, blank=True, help_text="the last progress notes, [[iso time, note], …]")
    return_value = models.JSONField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=500, null=True, blank=True, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "priority", "enqueued_at"], name="task_claim_idx"),
            models.Index(fields=["status", "finished_at"], name="task_finished_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.status}]"


class WorkerKind(models.TextChoices):
    WEB = "web"
    WATCHER = "watcher"
    WORKER = "worker"


class WorkerState(models.TextChoices):
    STARTING = "starting"
    IDLE = "idle"
    BUSY = "busy"
    STOPPING = "stopping"
    STOPPED = "stopped"


class Worker(models.Model):
    id = models.CharField(primary_key=True, max_length=64)
    pid = models.IntegerField()
    kind = models.CharField(max_length=20, choices=WorkerKind.choices, default=WorkerKind.WORKER)
    state = models.CharField(max_length=20, choices=WorkerState.choices, default=WorkerState.STARTING)
    started_at = models.DateTimeField()
    heartbeat_at = models.DateTimeField()
    current_task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    engine_command = models.CharField(
        max_length=300, null=True, blank=True, help_text="the Siril command running now"
    )

    def __str__(self) -> str:
        return f"{self.kind} {self.id} ({self.state})"


class ResourceSample(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="samples")
    cpu_pct = models.FloatField(help_text="the worker and its children")
    rss_bytes = models.BigIntegerField()
    engine_cpu_pct = models.FloatField(default=0, help_text="its Siril process, if any")
    engine_rss_bytes = models.BigIntegerField(default=0)
    at = models.DateTimeField(db_index=True)


class Lease(models.Model):
    """A named lease held by one process at a time (e.g. the watcher), renewed before it expires."""

    name = models.CharField(primary_key=True, max_length=100)
    holder = models.CharField(max_length=200)
    expires_at = models.DateTimeField()
