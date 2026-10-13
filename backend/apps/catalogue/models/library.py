"""Rigs and collections (spec 006). A rig is one telescope, camera and focal length; a collection groups the
datasets of one object across rigs, filters, framings and years. Catalogue-only: nothing moves on disk."""

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


class Project(models.Model):
    """One way of shooting a collection's object (006-DR-20): "6-panel mosaic 2026", "Single panel 2025"."""

    class Kind(models.TextChoices):
        SINGLE = "single", "Single field"
        MOSAIC = "mosaic", "Mosaic"

    collection = models.ForeignKey("catalogue.Collection", on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SINGLE)
    planned_panels = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="mosaics: panels planned"
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name


class Collection(models.Model):
    name = models.CharField(max_length=200)
    objects_text = models.CharField(
        max_length=500, blank=True, default="", help_text="e.g. NGC 7000 · IC 5070"
    )
    constellation = models.CharField(
        max_length=40, blank=True, default="", help_text="from the datasets' pointing"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name
