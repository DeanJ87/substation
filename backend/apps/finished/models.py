"""Finished projects and render tokens (spec 020).

A finished project is a folder in a library with the Completed role, `<kind>/<subject>/<name>/`, holding the owner's
hand-finished output. It links to the SubStation projects whose subs made it, and its files carry roles (final,
starless, ...) so a renderer can ask for "the final image" without guessing."""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProjectKind(models.TextChoices):
    ASTRO = "astro", "Astro"
    NIGHTSCAPES = "nightscapes", "Nightscapes"
    VIDEOS = "videos", "Videos"


KIND_FOLDERS = {
    "astro": ProjectKind.ASTRO,
    "nightscapes": ProjectKind.NIGHTSCAPES,
    "videos": ProjectKind.VIDEOS,
}
OUTPUT_SECTIONS = (
    "exports",
    "web",
    "social",
)  # served; project/ holds working files, listed but never served
SECTIONS = (*OUTPUT_SECTIONS, "project")


class FinishedProject(models.Model):
    library = models.ForeignKey(
        "libraries.Library", on_delete=models.CASCADE, related_name="finished_projects"
    )
    rel_path = models.CharField(max_length=1000, help_text="kind/subject/name inside the library")
    kind = models.CharField(max_length=12, choices=ProjectKind.choices)
    subject = models.CharField(max_length=300)
    name = models.CharField(max_length=300)
    linked_projects = models.ManyToManyField("catalogue.Project", blank=True, related_name="finished")
    processing = models.JSONField(default=list, blank=True, help_text="ordered processing step labels")
    missing = models.BooleanField(default=False, help_text="the folder was not found on the last scan")
    files_changed_at = models.DateTimeField(null=True, blank=True, help_text="newest change to its files")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    wrote_project_json_sha256 = models.CharField(max_length=64, blank=True, default="")
    data_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="020-DR-11: hash of everything that feeds the render data",
    )
    data_changed_at = models.DateTimeField(
        null=True, blank=True, help_text="when that fingerprint last changed"
    )

    class Meta:
        ordering = ["kind", "subject", "name"]
        constraints = [
            models.UniqueConstraint(fields=["library", "rel_path"], name="finished_project_path_unique")
        ]

    def __str__(self) -> str:
        return self.rel_path

    @property
    def changed_at(self):  # noqa: ANN201
        """When anything a renderer cares about last changed: its files, links, roles or processing."""
        return max(t for t in (self.files_changed_at, self.updated_at) if t is not None)


class FileRole(models.TextChoices):
    NONE = "", "No role"
    FINAL = "final", "Final"
    STARLESS = "starless", "Starless"
    STARS = "stars", "Stars only"
    PER_FILTER = "per_filter", "Single filter"
    PROGRESSIVE = "progressive", "Progressive stack"


class FinishedFile(models.Model):
    project = models.ForeignKey(FinishedProject, on_delete=models.CASCADE, related_name="files")
    rel_path = models.CharField(
        max_length=1000, help_text="inside the project folder, e.g. exports/heart-final.png"
    )
    section = models.CharField(max_length=10)
    size_bytes = models.BigIntegerField()
    mtime = models.FloatField()
    sha256 = models.CharField(max_length=64, blank=True, default="", help_text="filled when first served")
    missing = models.BooleanField(default=False)
    role = models.CharField(max_length=12, choices=FileRole.choices, blank=True, default=FileRole.NONE)
    role_filter = models.CharField(max_length=100, blank=True, default="", help_text="per_filter: the filter")
    role_order = models.PositiveIntegerField(null=True, blank=True, help_text="progressive: 1, 2, 3 ...")
    role_set_by_owner = models.BooleanField(default=False)

    class Meta:
        ordering = ["section", "rel_path"]
        constraints = [
            models.UniqueConstraint(fields=["project", "rel_path"], name="finished_file_path_unique")
        ]

    def __str__(self) -> str:
        return self.rel_path

    @property
    def ext(self) -> str:
        return self.rel_path.rsplit(".", 1)[-1].lower() if "." in self.rel_path else ""


class TokenScope(models.TextChoices):
    RENDER = "render", "Render: read finished projects"


TOKEN_PREFIX = "sst_"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiToken(models.Model):
    """A personal API token (020-FR-011): shown once, stored hashed, scoped, revocable."""

    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=20, choices=TokenScope.choices, default=TokenScope.RENDER)
    digest = models.CharField(max_length=64, unique=True)
    hint = models.CharField(max_length=12, help_text="the last characters, to tell tokens apart")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} (…{self.hint})"

    @classmethod
    def issue(
        cls, name: str, scope: str = TokenScope.RENDER, user=None, expires_at=None
    ) -> tuple[ApiToken, str]:  # noqa: ANN001
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        tok = cls.objects.create(
            name=name,
            scope=scope,
            digest=hash_token(raw),
            hint=raw[-4:],
            created_by=user,
            expires_at=expires_at,
        )
        return tok, raw

    @property
    def active(self) -> bool:
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)
