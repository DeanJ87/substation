"""Per-field metadata with its source, content-keyed user corrections and recorded conflicts
(constitution II; data-model.md)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class MetadataField(models.TextChoices):
    OBJECT = "object"
    TARGET = "target"
    PANEL = "panel"
    FILTER = "filter"
    EXPTIME = "exptime"
    CCD_TEMP = "ccd_temp"
    SET_TEMP = "set_temp"
    GAIN = "gain"
    OFFSET = "offset"
    XBIN = "xbin"
    YBIN = "ybin"
    CAMERA = "camera"
    TELESCOPE = "telescope"
    DATE_OBS = "date_obs"
    SITE_LAT = "site_lat"
    SITE_LON = "site_lon"
    FRAME_TYPE = "frame_type"


class MetadataSource(models.TextChoices):
    HEADER = "header"
    FOLDER_PATTERN = "folder_pattern"
    FILENAME_PATTERN = "filename_pattern"
    INFERRED = "inferred"
    SETTINGS = "settings"
    USER = "user"


class MetadataValue(models.Model):
    frame = models.ForeignKey("catalogue.Frame", on_delete=models.CASCADE, related_name="metadata")
    field = models.CharField(max_length=20, choices=MetadataField.choices)
    value = models.CharField(max_length=500, null=True, blank=True, help_text="normalised value as text")
    raw = models.CharField(max_length=500, null=True, blank=True, help_text="original text as found")
    source = models.CharField(max_length=20, choices=MetadataSource.choices)
    source_detail = models.CharField(
        max_length=200, blank=True, default="", help_text="keyword, pattern id, rule"
    )
    is_winner = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["frame", "field", "source", "source_detail"], name="metadata_unique_source"
            )
        ]
        indexes = [models.Index(fields=["frame", "field", "is_winner"], name="metadata_winner_idx")]


class ContentCorrection(models.Model):
    """A user value keyed by content, so it survives moves and applies to future identical files."""

    sha256 = models.CharField(max_length=64, db_index=True)
    field = models.CharField(max_length=20, choices=MetadataField.choices)
    value = models.CharField(max_length=500, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sha256", "field"], name="correction_unique_field")]


class HeaderConflict(models.Model):
    frame = models.ForeignKey("catalogue.Frame", on_delete=models.CASCADE, related_name="conflicts")
    field = models.CharField(max_length=20, choices=MetadataField.choices)
    values = models.JSONField(help_text="source -> value")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["frame", "field"], name="conflict_unique_field")]
