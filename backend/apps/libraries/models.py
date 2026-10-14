"""Libraries (read-only mounts under /data/library) and installation-wide settings."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class LibraryStatus(models.TextChoices):
    OK = "ok"
    UNREACHABLE = "unreachable"
    SCANNING = "scanning"


class Library(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text="directory name under /data/library")
    mount_path = models.CharField(max_length=1000)
    enabled = models.BooleanField(default=True)
    allow_delete = models.BooleanField(
        default=False,
        help_text="SubStation may move binned files to quarantine here and delete them (spec 011)",
    )
    site_name = models.CharField(max_length=200, null=True, blank=True)
    site_lat = models.FloatField(null=True, blank=True)
    site_lon = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=LibraryStatus.choices, default=LibraryStatus.OK)
    last_full_sweep_at = models.DateTimeField(null=True, blank=True)
    sweep_interval_active_s = models.PositiveIntegerField(default=60)
    sweep_interval_idle_s = models.PositiveIntegerField(default=900)
    rescan_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "libraries"

    def __str__(self) -> str:
        return self.name


class InstallationSettings(models.Model):
    """Singleton (pk=1): site fallback and filter aliases (data-model.md)."""

    site_name = models.CharField(max_length=200, null=True, blank=True)
    site_lat = models.FloatField(null=True, blank=True)
    site_lon = models.FloatField(null=True, blank=True)
    filter_aliases = models.JSONField(default=dict, blank=True, help_text='e.g. {"ha": "Hα"}')
    worker_count = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="null = SUBSTATION_WORKERS"
    )
    siril_heavy_slots = models.PositiveSmallIntegerField(default=1)
    queue_paused = models.BooleanField(default=False)
    work_budget_gb = models.FloatField(
        null=True, blank=True, help_text="intermediates for stacking; null = STACK_WORK_BUDGET_GB"
    )
    siril_threads = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="per Siril; null = all cores"
    )
    siril_mem_ratio = models.FloatField(
        null=True, blank=True, help_text="share of free memory each Siril may use; null = 0.9 ÷ workers"
    )
    stack_threads = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Siril threads while a stack or master build runs; null = every core"
    )
    stack_mem_ratio = models.FloatField(
        null=True,
        blank=True,
        help_text="share of free memory while stacking; null = SUBSTATION_SIRIL_HEAVY_MEM (0.8)",
    )
    work_used = models.JSONField(
        default=dict, blank=True, help_text="bytes in the work folder by part, measured by the supervisor"
    )
    processing = models.JSONField(
        default=dict, blank=True, help_text="calibration, grading and stacking settings"
    )
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "installation settings"

    @classmethod
    def load(cls) -> InstallationSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
