"""Rigs and collections (spec 006). A rig is one telescope, camera and focal length; a collection groups the
datasets of one object across rigs, filters, framings and years. Grouping is catalogue-only: nothing moves on disk
unless the owner archives a collection or brings one back (spec 013, models in moves.py)."""

from __future__ import annotations

from django.db import models


class Rig(models.Model):
    key = models.CharField(
        max_length=500, unique=True, help_text="telescope|camera|focal length, from headers"
    )
    name = models.CharField(max_length=200)
    telescope = models.CharField(max_length=200, blank=True, default="")
    camera = models.CharField(max_length=200, blank=True, default="")
    focal_mm = models.FloatField(null=True, blank=True)
    pixel_um = models.FloatField(null=True, blank=True)
    renamed = models.BooleanField(default=False)
    mount = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="equatorial, alt-az, star tracker or smart telescope; blank = not said",
    )
    calibration = models.CharField(
        max_length=10,
        choices=[
            ("masters", "Masters"),
            ("flats", "Flats and bias, no darks"),
            ("none", "None: calibrated in the camera"),
        ],
        default="masters",
        help_text="smart telescopes such as the Seestar calibrate in the device; uncooled cameras often go without darks",
    )

    def __str__(self) -> str:
        return self.name

    @property
    def image_scale(self) -> float | None:
        if not self.focal_mm or not self.pixel_um:
            return None
        return 206.265 * self.pixel_um / self.focal_mm


def project_label(season: str, own_name: str) -> str:
    """How a project is called: its season, then its own name if it has one ("2026", "2026 · Askar")."""
    return " · ".join(x for x in (season, own_name) if x) or "Project"


class Project(models.Model):
    """One season of shooting a collection's object (006-DR-20, amendment 2026-10-22): "2026", "2025–26 · widefield".
    The kind is worked out (a mosaic when panels are planned or shot) unless the owner says otherwise."""

    class Kind(models.TextChoices):
        SINGLE = "single", "Single field"
        MOSAIC = "mosaic", "Mosaic"

    collection = models.ForeignKey("catalogue.Collection", on_delete=models.CASCADE, related_name="projects")
    own_name = models.CharField(
        max_length=200, blank=True, default="", help_text="optional, after the season"
    )
    season = models.CharField(
        max_length=20, blank=True, default="", help_text='"2026", or "2025–26" over New Year'
    )
    kind_override = models.CharField(
        max_length=10,
        choices=Kind.choices,
        null=True,
        blank=True,
        help_text="the owner's choice; empty = automatic",
    )
    planned_panels = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="mosaics: panels planned"
    )
    position = models.PositiveIntegerField(default=0)
    goals = models.JSONField(
        default=dict, blank=True, help_text="hours of usable integration wanted, per filter"
    )
    done_at = models.DateTimeField(null=True, blank=True, help_text="the owner finished shooting it")
    needs_review = models.BooleanField(
        default=False, help_text="held apart when seasons were joined; the owner decides"
    )
    review_reason = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return project_label(self.season, self.own_name)

    @name.setter
    def name(self, value: str) -> None:
        self.own_name = (value or "").strip()

    @property
    def kind_auto(self) -> str:
        """A mosaic when more than one panel is planned or shot, else a single field."""
        if (self.planned_panels or 0) > 1:
            return self.Kind.MOSAIC
        if self.pk and self.datasets.exclude(panel=None).values("panel").distinct().count() > 1:
            return self.Kind.MOSAIC
        return self.Kind.SINGLE

    @property
    def kind(self) -> str:
        """The owner's choice wins (020-DR-10); otherwise worked out."""
        return self.kind_override or self.kind_auto

    @kind.setter
    def kind(self, value: str | None) -> None:
        self.kind_override = value or None


class Collection(models.Model):
    name = models.CharField(max_length=200)
    objects_text = models.CharField(
        max_length=500, blank=True, default="", help_text="e.g. NGC 7000 · IC 5070"
    )
    constellation = models.CharField(
        max_length=40, blank=True, default="", help_text="from the datasets' pointing"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archive_dismissed_at = models.DateTimeField(
        null=True, blank=True, help_text="the owner said not to suggest archiving it (spec 013 FR-010)"
    )

    def __str__(self) -> str:
        return self.name
