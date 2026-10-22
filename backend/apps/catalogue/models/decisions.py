"""Human verdicts and the reconciliation list (constitution III, V, VIII; data-model.md)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Verdict(models.TextChoices):
    REJECT = "reject"
    ACCEPT = "accept"
    KEEP = "keep"  # keep, down-weighted
    AUTO = "auto"  # the user reverted to the machine grade (spec 003: overrides are logged, never deleted)


class VerdictSource(models.TextChoices):
    NINA_BAD_PREFIX = "nina_bad_prefix"
    OVERRIDE = "override"


class UserVerdict(models.Model):
    frame = models.ForeignKey("catalogue.Frame", on_delete=models.CASCADE, related_name="verdicts")
    verdict = models.CharField(max_length=10, choices=Verdict.choices)
    source = models.CharField(max_length=20, choices=VerdictSource.choices)
    copy = models.ForeignKey(
        "catalogue.Copy", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["frame", "created_at"], name="verdict_frame_idx")]


class ReconciliationKind(models.TextChoices):
    MISSING_FIELD = "missing_field"
    FRAME_MISSING = "frame_missing"
    MASTER_METADATA = "master_metadata"
    AMBIGUOUS_MASTER = "ambiguous_master"
    CLASSIFICATION_UNKNOWN = "classification_unknown"
    BAD_WITHOUT_TWIN = "bad_without_twin"  # informational


class ReconciliationStatus(models.TextChoices):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReconciliationItem(models.Model):
    kind = models.CharField(max_length=30, choices=ReconciliationKind.choices)
    frame = models.ForeignKey(
        "catalogue.Frame",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_items",
    )
    dataset = models.ForeignKey(
        "catalogue.Dataset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    field = models.CharField(max_length=20, blank=True, default="", help_text="empty when not field-specific")
    reason = models.TextField()
    suggestion = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ReconciliationStatus.choices, default=ReconciliationStatus.OPEN
    )
    resolution = models.JSONField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "kind"], name="recon_status_kind_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "frame", "field"],
                condition=models.Q(status="open"),
                name="recon_one_open_per_issue",
            )
        ]


class Change(models.Model):
    """One change made by hand, kept so it can be undone (spec 016): verdicts set, grades agreed with, files binned,
    datasets moved between collections, failed jobs dismissed, calibration frames' QA overridden.
    `data` holds what undoing needs (the verdict rows added, the files binned); undoing never rewrites history,
    it removes this change's own rows or reverses its own moves."""

    class Kind(models.TextChoices):
        VERDICT = "verdict"
        AGREE = "agree"
        BIN = "bin"
        MOVE = "move"  # datasets moved to another collection (or out of one)
        DISMISS = "dismiss"  # failed jobs dismissed from Activity
        QA = "qa"  # your QA choice on raw calibration frames
        ARCHIVE = "archive"  # a collection's files moved to its archive library or back (spec 013)
        PROJECT = "project"  # projects merged, split, removed, edited or datasets moved between them

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    summary = models.CharField(max_length=200)
    data = models.JSONField(default=dict)
    count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"], name="change_user_idx")]
