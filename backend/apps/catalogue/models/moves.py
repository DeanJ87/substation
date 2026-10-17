"""Archiving a collection and bringing it back (spec 013): a move of its files from one library to another, and
one row per file copy it moves, so a move interrupted by a restart carries on where it stopped."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class MoveDirection(models.TextChoices):
    ARCHIVE = "archive", "Archive"
    BRING_BACK = "bring_back", "Bring back"


class MoveState(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


ACTIVE_MOVE_STATES = (MoveState.QUEUED, MoveState.RUNNING)


class CollectionMove(models.Model):
    collection = models.ForeignKey("catalogue.Collection", on_delete=models.CASCADE, related_name="moves")
    direction = models.CharField(max_length=12, choices=MoveDirection.choices)
    from_library = models.ForeignKey("libraries.Library", on_delete=models.CASCADE, related_name="+")
    to_library = models.ForeignKey("libraries.Library", on_delete=models.CASCADE, related_name="+")
    state = models.CharField(max_length=10, choices=MoveState.choices, default=MoveState.QUEUED)
    planned = models.BooleanField(default=False, help_text="its files were chosen when it first ran")
    files_total = models.PositiveIntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    files_done = models.PositiveIntegerField(default=0)
    bytes_done = models.BigIntegerField(default=0)
    problems = models.PositiveIntegerField(
        default=0, help_text="files left where they were, with a reason each"
    )
    error = models.TextField(blank=True, default="")
    task = models.ForeignKey(
        "substation_tasks.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["collection", "state"], name="move_collection_state_idx")]

    def __str__(self) -> str:
        return f"{self.direction} {self.collection_id} [{self.state}]"


class MoveItemState(models.TextChoices):
    PENDING = "pending"
    DONE = "done"
    PROBLEM = "problem"  # left where it was; `reason` says why


class MoveItem(models.Model):
    move = models.ForeignKey(CollectionMove, on_delete=models.CASCADE, related_name="items")
    frame = models.ForeignKey("catalogue.Frame", on_delete=models.CASCADE, related_name="+")
    rel_path = models.CharField(max_length=2000, help_text="the same in both libraries")
    size_bytes = models.BigIntegerField(default=0)
    calibration = models.BooleanField(default=False, help_text="a calibration frame, not one of its lights")
    state = models.CharField(max_length=10, choices=MoveItemState.choices, default=MoveItemState.PENDING)
    reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["move", "state"], name="moveitem_move_state_idx")]
