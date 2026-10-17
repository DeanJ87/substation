"""Whether SubStation may write to a library, and why not (specs 011 and 013).

A library mounted read-write is writable for everything that writes: the bin's quarantine and deleting, archiving
to it and bringing collections back from it. One mounted read-only is never written to. Which setting mounts it
read-write depends on its slot in the reference compose file, which tells the containers the slots' folder names in
SUBSTATION_LIBRARY_NAMES ("library,archive,.no-library-3"), so the reason can name the right variable."""

from __future__ import annotations

import os

from django.conf import settings


def is_writable(lib) -> bool:  # noqa: ANN001
    return os.access(lib.mount_path, os.W_OK)


def mode_variable(name: str) -> str | None:
    """The compose variable that mounts library `name` read-write, or None when it isn't one of the slots."""
    names = [n.strip() for n in (getattr(settings, "LIBRARY_NAMES", "") or "").split(",")]
    if name not in names:
        return None
    i = names.index(name)
    return "SUBSTATION_LIBRARY_MODE" if i == 0 else f"SUBSTATION_LIBRARY_{i + 1}_MODE"


def read_only_reason(lib) -> str | None:  # noqa: ANN001
    """Why SubStation can't write here, in a sentence the Settings page shows next to what it disables."""
    if is_writable(lib):
        return None
    var = mode_variable(lib.name)
    how = f"{var}=rw" if var else "its volume line ending :rw"
    return f"Mounted read-only. Mount it read-write ({how}) to allow this."
