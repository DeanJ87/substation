"""User path patterns (T072; contracts/path-patterns.md): fill metadata from folder and file names when headers
are missing or wrong. They never touch files."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PatternKind(models.TextChoices):
    FOLDER = "folder"
    FILENAME = "filename"


class PathPattern(models.Model):
    library = models.ForeignKey(
        "libraries.Library",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="patterns",
        help_text="null: every library",
    )
    scope_glob = models.CharField(max_length=500, default="**", help_text="which paths it applies to")
    kind = models.CharField(max_length=10, choices=PatternKind.choices)
    pattern = models.CharField(max_length=500)
    prefer_over_header = models.JSONField(
        default=list, blank=True, help_text="fields where it beats the header"
    )
    priority = models.IntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "id"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.kind} {self.pattern}"
