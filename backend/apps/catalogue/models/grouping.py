"""Nights, datasets (multi-year), per-night summaries and calibration sets (data-model.md)."""

from __future__ import annotations

from django.db import models


class Night(models.Model):
    site_key = models.CharField(max_length=40, help_text="rounded lat,lon")
    date = models.DateField()
    site_lat = models.FloatField(null=True, blank=True)
    site_lon = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site_key", "date"], name="night_unique_site_date")]

    def __str__(self) -> str:
        return f"{self.date} @ {self.site_key}"


class DatasetState(models.TextChoices):
    OK = "ok"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    AWAITING_CALIBRATION = "awaiting_calibration"
    INTEGRATING = "integrating"
    STALE = "stale"


class Dataset(models.Model):
    # Uniqueness lives in group_key, built in code from the grouping fields. A multi-column unique
    # constraint cannot be used: the key contains NULLs (no panel, no gain), which a unique index treats as
    # distinct unless NULLS NOT DISTINCT.
    group_key = models.CharField(max_length=1000, unique=True)
    target = models.CharField(max_length=300)
    panel = models.PositiveSmallIntegerField(null=True, blank=True)
    filter_norm = models.CharField(max_length=100)
    camera = models.CharField(max_length=200, blank=True, default="")
    telescope = models.CharField(max_length=200, blank=True, default="")
    xbin = models.PositiveSmallIntegerField(default=1)
    ybin = models.PositiveSmallIntegerField(default=1)
    gain = models.IntegerField(null=True, blank=True)
    offset = models.IntegerField(null=True, blank=True)
    display_name = models.CharField(max_length=500)
    state = models.CharField(max_length=30, choices=DatasetState.choices, default=DatasetState.OK)
    # effective verdicts of catalogued lights (spec 003): accepted, down-weighted, rejected, not graded yet
    rig = models.ForeignKey(
        "catalogue.Rig", null=True, blank=True, on_delete=models.SET_NULL, related_name="datasets"
    )
    collection = models.ForeignKey(
        "catalogue.Collection", null=True, blank=True, on_delete=models.SET_NULL, related_name="datasets"
    )
    project = models.ForeignKey(
        "catalogue.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="datasets"
    )
    project_position = models.PositiveIntegerField(null=True, blank=True)
    accepted_count = models.PositiveIntegerField(default=0)
    down_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    awaiting_count = models.PositiveIntegerField(default=0, help_text="lights waiting for calibration")
    accepted_integration_s = models.FloatField(default=0, help_text="accepted and down-weighted exposure")
    rejected_integration_s = models.FloatField(default=0, help_text="rejected exposure")
    manual_count = models.PositiveIntegerField(default=0)
    state_reason = models.TextField(blank=True, default="")
    sub_count = models.PositiveIntegerField(default=0)
    user_rejected_count = models.PositiveIntegerField(default=0)
    integration_s = models.FloatField(default=0)
    first_utc = models.DateTimeField(null=True, blank=True)
    last_utc = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.display_name


class DatasetNight(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="nights")
    night = models.ForeignKey(Night, on_delete=models.CASCADE, related_name="dataset_nights")
    sub_count = models.PositiveIntegerField(default=0)
    user_rejected_count = models.PositiveIntegerField(default=0)
    integration_s = models.FloatField(default=0)
    first_utc = models.DateTimeField(null=True, blank=True)
    last_utc = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "night"], name="dataset_night_unique")]


class CalibrationSet(models.Model):
    """Created with the foundational models because Frame references it."""

    type = models.CharField(max_length=20)
    camera = models.CharField(max_length=200, blank=True, default="")
    filter_norm = models.CharField(max_length=100, null=True, blank=True)
    exptime_s = models.FloatField()
    gain = models.IntegerField(null=True, blank=True)
    offset = models.IntegerField(null=True, blank=True)
    xbin = models.PositiveSmallIntegerField(default=1)
    ybin = models.PositiveSmallIntegerField(default=1)
    set_temp_c = models.FloatField(null=True, blank=True)
    session_start_utc = models.DateTimeField()
    session_end_utc = models.DateTimeField()
    night = models.ForeignKey(
        Night, null=True, blank=True, on_delete=models.SET_NULL, related_name="calibration_sets"
    )
    frame_count = models.PositiveIntegerField(default=0)
    filter_blocks = models.JSONField(default=dict, help_text="darks: frames per NINA filter label")

    class Meta:
        indexes = [models.Index(fields=["type", "exptime_s", "session_start_utc"], name="calset_lookup_idx")]
