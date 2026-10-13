"""Per-light processing state (specs 002–004): the calibration match, the measurement of the calibrated sub,
the machine grade, and masters (stacks) with their members. Human verdicts stay in catalogue.UserVerdict."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class MatchState(models.TextChoices):
    MATCHED = "matched"
    AWAITING = "awaiting"


class CalibrationMatch(models.Model):
    """Which master dark and flat calibrate a light, and why (spec 002 US1)."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="calibration"
    )
    state = models.CharField(max_length=10, choices=MatchState.choices)
    dark = models.ForeignKey(
        "catalogue.Frame", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    flat = models.ForeignKey(
        "catalogue.Frame", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.TextField(blank=True, default="", help_text="why it's waiting, in plain English")
    dark_note = models.CharField(max_length=200, blank=True, default="")  # "Exact match", "0.1 °C apart"
    flat_note = models.CharField(
        max_length=200, blank=True, default=""
    )  # "12 days before", "Weak: 33 days before"
    weak = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False, help_text="the user chose these frames (Change)")
    pending_flat_set = models.ForeignKey(
        "catalogue.CalibrationSet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="a chosen flat set whose master is being built",
    )
    updated_at = models.DateTimeField(auto_now=True)


class MeasureState(models.TextChoices):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"


class SubMeasurement(models.Model):
    """The calibrated sub and what SubStation measured on it (spec 003 FR-001, FR-002)."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="measurement"
    )
    state = models.CharField(max_length=10, choices=MeasureState.choices, default=MeasureState.QUEUED)
    error = models.TextField(null=True, blank=True)
    dark = models.ForeignKey(
        "catalogue.Frame", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    flat = models.ForeignKey(
        "catalogue.Frame", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    calibrated_path = models.CharField(max_length=1000, blank=True, default="")
    preview_path = models.CharField(max_length=1000, blank=True, default="")
    stars = models.IntegerField(null=True, blank=True)
    fwhm_px = models.FloatField(null=True, blank=True)
    fwhm_arcsec = models.FloatField(null=True, blank=True)
    roundness = models.FloatField(null=True, blank=True, help_text="median minor/major FWHM")
    eccentricity = models.FloatField(null=True, blank=True)
    background = models.FloatField(null=True, blank=True, help_text="median ADU of the calibrated sub")
    noise = models.FloatField(null=True, blank=True, help_text="background noise, ADU")
    snr = models.FloatField(null=True, blank=True)
    pixel_scale = models.FloatField(null=True, blank=True, help_text="arcsec per pixel")
    engine_version = models.CharField(max_length=100, blank=True, default="")
    seconds = models.FloatField(null=True, blank=True)
    measured_at = models.DateTimeField(null=True, blank=True)


class GradeVerdict(models.TextChoices):
    ACCEPT = "accept"
    DOWN = "down"
    REJECT = "reject"


class MachineGrade(models.Model):
    """SubStation's grade, against the sub's own session (spec 003 FR-003, FR-004). Never a human decision."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="grade"
    )
    verdict = models.CharField(max_length=10, choices=GradeVerdict.choices)
    weight = models.FloatField(default=1.0)
    reason = models.TextField()
    provisional = models.BooleanField(default=False)
    near_threshold = models.BooleanField(default=False, help_text="within 10% of a threshold (Review)")
    wfwhm_px = models.FloatField(null=True, blank=True)
    session_medians = models.JSONField(default=dict)
    thresholds_version = models.IntegerField(default=1)
    graded_at = models.DateTimeField(auto_now=True)


class MasterState(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    CURRENT = "current"
    SUPERSEDED = "superseded"
    STALE = "stale"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"  # its file is gone; the row stays as the record of who deleted it and when


class Master(models.Model):
    """One integration of a dataset (spec 004, "Master v3"), kept with the recipe that made it."""

    dataset = models.ForeignKey("catalogue.Dataset", on_delete=models.CASCADE, related_name="masters")
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=12, choices=MasterState.choices, default=MasterState.QUEUED)
    state_reason = models.TextField(blank=True, default="")
    recipe = models.JSONField(default=dict, help_text="scope, rule, options; enough to re-run")
    step = models.CharField(max_length=30, blank=True, default="")
    progress = models.FloatField(default=0)
    sub_count = models.PositiveIntegerField(default=0)
    session_count = models.PositiveIntegerField(default=0)
    integration_s = models.FloatField(default=0)
    output_path = models.CharField(max_length=1000, blank=True, default="")
    preview_path = models.CharField(max_length=1000, blank=True, default="")
    report = models.JSONField(default=dict)
    solve = models.JSONField(
        default=dict, blank=True, help_text="plate solve of the master: ra, dec, rotation, flipped, fov"
    )
    error = models.TextField(null=True, blank=True)
    engine_version = models.CharField(max_length=100, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    task = models.ForeignKey(
        "substation_tasks.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "version"], name="master_version_unique")]


class MasterMember(models.Model):
    master = models.ForeignKey(Master, on_delete=models.CASCADE, related_name="members")
    frame = models.ForeignKey("catalogue.Frame", on_delete=models.CASCADE, related_name="+")
    included = models.BooleanField(default=True)
    weight = models.FloatField(default=1.0)
    reason = models.CharField(max_length=300, blank=True, default="")


class QAVerdict(models.TextChoices):
    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"


class CalibrationQA(models.Model):
    """QA of one raw calibration frame against its own set (spec 002 US2)."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="qa"
    )
    verdict = models.CharField(max_length=10, choices=QAVerdict.choices)
    reason = models.TextField(blank=True, default="")
    stats = models.JSONField(default=dict)
    thumb_path = models.CharField(max_length=1000, blank=True, default="")
    override = models.CharField(max_length=10, blank=True, default="", help_text="the user's verdict, if any")
    checked_at = models.DateTimeField(auto_now=True)


class BuiltMaster(models.Model):
    """A master SubStation built from a raw calibration set (spec 002 US3), with its provenance and report."""

    calibration_set = models.ForeignKey(
        "catalogue.CalibrationSet", on_delete=models.CASCADE, related_name="built"
    )
    frame = models.ForeignKey(
        "catalogue.Frame", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    state = models.CharField(max_length=12, default="queued")  # queued, running, done, failed, blocked
    reason = models.TextField(blank=True, default="")
    method = models.CharField(max_length=300, blank=True, default="")
    calibrated_with = models.ForeignKey(
        "catalogue.Frame",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="the master bias or dark flat used on flats",
    )
    frames_used = models.PositiveIntegerField(default=0)
    frames_excluded = models.JSONField(default=list)
    output_path = models.CharField(max_length=1000, blank=True, default="")
    preview_path = models.CharField(max_length=1000, blank=True, default="")
    report = models.JSONField(default=dict)
    engine_version = models.CharField(max_length=100, blank=True, default="")
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class SolveState(models.TextChoices):
    SOLVED = "solved"
    FAILED = "failed"


class PlateSolve(models.Model):
    """Where a light actually points (spec 009): Siril's solve against the local star catalogues."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="solve"
    )
    state = models.CharField(max_length=10, choices=SolveState.choices)
    ra_deg = models.FloatField(null=True, blank=True)
    dec_deg = models.FloatField(null=True, blank=True)
    rotation_deg = models.FloatField(
        null=True, blank=True, help_text="position angle of the image's up direction"
    )
    flipped = models.BooleanField(
        null=True, blank=True, help_text="the image is mirrored relative to the sky"
    )
    source = models.CharField(
        max_length=12, blank=True, default="", help_text="calibrated or raw: the file solved"
    )
    scale_arcsec = models.FloatField(null=True, blank=True, help_text="arcsec per pixel")
    fov_w_deg = models.FloatField(null=True, blank=True)
    fov_h_deg = models.FloatField(null=True, blank=True)
    solver = models.CharField(max_length=40, default="Siril")
    seconds = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True, default="", help_text="why it failed, in plain English")
    solved_at = models.DateTimeField(auto_now=True)


class MasterWindow(models.Model):
    """When a calibration master may be used (002 C13): nights outside the window don't match it, e.g. flats from
    before the camera was rotated or dust was cleaned."""

    frame = models.OneToOneField(
        "catalogue.Frame", on_delete=models.CASCADE, primary_key=True, related_name="window"
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    set_at = models.DateTimeField(auto_now=True)


class CombinedMaster(models.Model):
    """One master per filter for a collection, every dataset's current master registered to the reference
    framing and, where several share a filter, averaged by integration (004-DR-05, T022)."""

    collection = models.ForeignKey("catalogue.Collection", on_delete=models.CASCADE, related_name="combined")
    project = models.ForeignKey(
        "catalogue.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="combined"
    )
    filter_norm = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=12, choices=MasterState.choices, default=MasterState.QUEUED)
    state_reason = models.TextField(blank=True, default="")
    reference = models.ForeignKey(
        "Master", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    inputs = models.JSONField(
        default=list, help_text="[{master, dataset, label, integration_s, subs, registered}]"
    )
    integration_s = models.FloatField(default=0)
    output_path = models.CharField(max_length=1000, blank=True, default="")
    preview_path = models.CharField(max_length=1000, blank=True, default="")
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    task = models.ForeignKey(
        "substation_tasks.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
