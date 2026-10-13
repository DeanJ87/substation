"""Frames (unique content), copies (paths), movement history and raw headers (data-model.md)."""

from __future__ import annotations

from django.db import models


class FrameType(models.TextChoices):
    LIGHT = "light"
    FLAT = "flat"
    DARK = "dark"
    DARK_FLAT = "dark_flat"
    BIAS = "bias"
    MASTER_DARK = "master_dark"
    MASTER_FLAT = "master_flat"
    MASTER_BIAS = "master_bias"
    MASTER_DARK_FLAT = "master_dark_flat"
    MASTER_LIGHT = (
        "master_light"  # a stack made elsewhere (PixInsight masterLight, Seestar stacked): not a sub
    )
    PROCESSED = (
        "processed"  # a sub already calibrated or registered by other software (WBPP _c/_r files): not raw
    )
    UNKNOWN = "unknown"


CALIBRATION_TYPES = {FrameType.FLAT, FrameType.DARK, FrameType.DARK_FLAT, FrameType.BIAS}
MASTER_TYPES = {
    FrameType.MASTER_DARK,
    FrameType.MASTER_FLAT,
    FrameType.MASTER_BIAS,
    FrameType.MASTER_DARK_FLAT,
}


class FrameFormat(models.TextChoices):
    FITS = "fits"
    FITS_COMPRESSED = "fits_compressed"
    XISF = "xisf"


class FrameStatus(models.TextChoices):
    PENDING = "pending"  # hashed; headers not read yet
    CATALOGUED = "catalogued"
    MISSING = "missing"
    IGNORED = "ignored"
    ERROR = "error"


class ClassificationSource(models.TextChoices):
    HEADER = "header"
    RULE = "rule"
    PATH_PATTERN = "path_pattern"
    USER = "user"  # stored as a user MetadataValue for frame_type with user and time


class Frame(models.Model):
    sha256 = models.CharField(primary_key=True, max_length=64)
    size_bytes = models.BigIntegerField()
    format = models.CharField(max_length=20, choices=FrameFormat.choices)
    image_count = models.PositiveSmallIntegerField(default=1)
    integration_index = models.PositiveSmallIntegerField(null=True, blank=True)
    frame_type = models.CharField(max_length=20, choices=FrameType.choices, default=FrameType.UNKNOWN)
    classification_reason = models.TextField(blank=True, default="")
    classification_source = models.CharField(
        max_length=20, choices=ClassificationSource.choices, default=ClassificationSource.HEADER
    )
    status = models.CharField(max_length=20, choices=FrameStatus.choices, default=FrameStatus.PENDING)
    error = models.TextField(null=True, blank=True)

    # Resolved values: denormalised winners of MetadataValue (the source of truth)
    object = models.CharField(max_length=300, null=True, blank=True)
    target = models.CharField(max_length=300, null=True, blank=True)
    panel = models.PositiveSmallIntegerField(null=True, blank=True)
    filter_raw = models.CharField(max_length=100, null=True, blank=True)
    filter_norm = models.CharField(max_length=100, null=True, blank=True)
    exptime_s = models.FloatField(null=True, blank=True)
    ccd_temp_c = models.FloatField(null=True, blank=True)
    set_temp_c = models.FloatField(null=True, blank=True)
    gain = models.IntegerField(null=True, blank=True)
    offset = models.IntegerField(null=True, blank=True)
    xbin = models.PositiveSmallIntegerField(null=True, blank=True)
    ybin = models.PositiveSmallIntegerField(null=True, blank=True)
    camera = models.CharField(max_length=200, null=True, blank=True)
    telescope = models.CharField(max_length=200, null=True, blank=True)
    date_obs_utc = models.DateTimeField(null=True, blank=True)
    site_lat = models.FloatField(null=True, blank=True)
    site_lon = models.FloatField(null=True, blank=True)

    night = models.ForeignKey(
        "catalogue.Night", null=True, blank=True, on_delete=models.SET_NULL, related_name="frames"
    )
    dataset = models.ForeignKey(
        "catalogue.Dataset", null=True, blank=True, on_delete=models.SET_NULL, related_name="frames"
    )
    calibration_set = models.ForeignKey(
        "catalogue.CalibrationSet", null=True, blank=True, on_delete=models.SET_NULL, related_name="frames"
    )
    first_seen_at = models.DateTimeField()
    catalogued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["dataset", "date_obs_utc"], name="frame_dataset_time_idx"),
            models.Index(fields=["night"], name="frame_night_idx"),
            models.Index(fields=["frame_type", "filter_norm", "exptime_s"], name="frame_type_filter_exp_idx"),
            models.Index(fields=["status"], name="frame_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.frame_type} {self.sha256[:12]}"


class Copy(models.Model):
    frame = models.ForeignKey(Frame, on_delete=models.CASCADE, related_name="copies")
    library = models.ForeignKey("libraries.Library", on_delete=models.CASCADE, related_name="copies")
    rel_path = models.CharField(max_length=2000)
    st_dev = models.BigIntegerField()
    st_ino = models.BigIntegerField()
    st_size = models.BigIntegerField()
    st_mtime_ns = models.BigIntegerField()
    is_bad_prefixed = models.BooleanField(default=False)
    present = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    missing_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["library", "rel_path"], name="copy_unique_path")]
        indexes = [models.Index(fields=["st_dev", "st_ino"], name="copy_inode_idx")]

    def __str__(self) -> str:
        return f"{self.library_id}:{self.rel_path}"


class CopyEventKind(models.TextChoices):
    DISCOVERED = "discovered"
    COPIED = "copied"
    MOVED = "moved"
    RENAMED = "renamed"
    REPLACED = "replaced"
    MISSING = "missing"
    REAPPEARED = "reappeared"


class CopyEvent(models.Model):
    kind = models.CharField(max_length=20, choices=CopyEventKind.choices)
    frame = models.ForeignKey(Frame, null=True, on_delete=models.SET_NULL, related_name="history")
    copy = models.ForeignKey(Copy, null=True, on_delete=models.SET_NULL, related_name="events")
    library = models.ForeignKey("libraries.Library", null=True, on_delete=models.SET_NULL, related_name="+")
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class HeaderSnapshot(models.Model):
    frame = models.ForeignKey(Frame, on_delete=models.CASCADE, related_name="headers")
    image_index = models.PositiveSmallIntegerField(default=0)
    image_id = models.CharField(max_length=200, blank=True, default="")
    geometry = models.CharField(max_length=100, blank=True, default="")
    sample_format = models.CharField(max_length=50, blank=True, default="")
    keywords = models.JSONField(default=dict)
    properties = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["frame", "image_index"], name="header_unique_image")]
