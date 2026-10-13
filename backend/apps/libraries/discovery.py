"""Discover libraries: every subdirectory of /data/library is a read-only Library (contracts/container.md)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings

from .models import InstallationSettings, Library, LibraryStatus

log = logging.getLogger(__name__)


def library_root() -> Path:
    return Path(settings.LIBRARY_ROOT)


def is_reachable(path: Path) -> bool:
    """A library is reachable if its directory can be listed and is not an empty mount point.

    An unmounted share usually appears as an empty directory; treating it as reachable would mark every
    frame in it missing (research R6), so an empty library is reported unreachable.
    """
    try:
        with os.scandir(path) as it:
            return next(it, None) is not None
    except OSError:
        return False


def discover_libraries() -> list[Library]:
    root = library_root()
    found: list[Library] = []
    names: set[str] = set()
    if root.is_dir():
        for entry in sorted(os.scandir(root), key=lambda e: e.name):
            if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=True):
                continue
            names.add(entry.name)
            lib, created = Library.objects.get_or_create(name=entry.name, defaults={"mount_path": entry.path})
            if not created and lib.mount_path != entry.path:
                lib.mount_path = entry.path
                lib.save(update_fields=["mount_path"])
            if created:
                log.info("Found library %s at %s", entry.name, entry.path)
            found.append(lib)
    gone = Library.objects.exclude(name__in=names).exclude(status=LibraryStatus.UNREACHABLE)
    for lib in gone:
        log.warning("Library %s is no longer mounted; nothing in it will be marked missing.", lib.name)
    gone.update(status=LibraryStatus.UNREACHABLE)
    return found


def seed_installation_settings() -> InstallationSettings:
    """Fill the site fallback from SUBSTATION_SITE_* the first time; later edits in Settings win."""
    s = InstallationSettings.load()
    changed = []
    for field, var, cast in (
        ("site_name", "SUBSTATION_SITE_NAME", str),
        ("site_lat", "SUBSTATION_SITE_LAT", float),
        ("site_lon", "SUBSTATION_SITE_LON", float),
    ):
        value = os.environ.get(var)
        if value and getattr(s, field) is None:
            setattr(s, field, cast(value))
            changed.append(field)
    if changed:
        s.save(update_fields=changed)
    return s
