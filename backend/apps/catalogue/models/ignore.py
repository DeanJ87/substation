"""Ignore rules (T089; FR-016): folders, globs and content the user doesn't want processed. Content rules
follow the content to any path."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class IgnoreKind(models.TextChoices):
    FOLDER = "folder"  # value: folder path inside the library
    GLOB = "glob"  # value: glob matched against the path inside the library, or the file name
    CONTENT = "content"  # value: sha256


class IgnoreRule(models.Model):
    kind = models.CharField(max_length=10, choices=IgnoreKind.choices)
    library = models.ForeignKey(
        "libraries.Library", null=True, blank=True, on_delete=models.CASCADE, related_name="ignore_rules"
    )
    value = models.CharField(max_length=1000)
    note = models.CharField(max_length=500, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "value"], name="ignore_kind_value_idx")]

    def __str__(self) -> str:
        return f"ignore {self.kind} {self.value}"
