"""T102 (quickstart V1, SC-004, FR-002): SubStation never writes to a library. Every file is hashed and
stat'ed before and after a full ingest, and while it runs any write-mode open under the library raises."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers"

pytestmark = pytest.mark.django_db(transaction=True)

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (
                hashlib.sha256(p.read_bytes()).hexdigest(),
                st.st_size,
                st.st_mtime_ns,
            )
    return out


def install_guard(mp: pytest.MonkeyPatch) -> list[str]:
    """Make any attempt to open a library file for writing, or to change one, fail and be recorded."""
    lib_root = str(Path(settings.LIBRARY_ROOT).resolve())
    attempts: list[str] = []

    def inside(path: object) -> bool:
        try:
            return os.path.realpath(os.fspath(path)).startswith(lib_root)  # type: ignore[call-overload]
        except TypeError:
            return False

    real_open, real_os_open, real_io_open = builtins.open, os.open, io.open

    def check_mode(file: object, mode: str) -> None:
        if inside(file) and any(c in mode for c in "wax+"):
            attempts.append(f"open({file}, {mode!r})")
            raise PermissionError(f"write to library: {file}")

    def g_open(file, mode="r", *a, **k):  # noqa: ANN001, ANN202
        check_mode(file, mode)
        return real_open(file, mode, *a, **k)

    def g_io_open(file, mode="r", *a, **k):  # noqa: ANN001, ANN202
        check_mode(file, mode)
        return real_io_open(file, mode, *a, **k)

    def g_os_open(path, flags, *a, **k):  # noqa: ANN001, ANN202
        if inside(path) and flags & WRITE_FLAGS:
            attempts.append(f"os.open({path}, {flags})")
            raise PermissionError(f"write to library: {path}")
        return real_os_open(path, flags, *a, **k)

    def refuse(name: str):  # noqa: ANN202
        real = getattr(os, name)

        def f(*a, **k):  # noqa: ANN002, ANN003, ANN202
            if any(inside(x) for x in a[:2]):
                attempts.append(f"os.{name}{a[:2]}")
                raise PermissionError(f"{name} in library")
            return real(*a, **k)

        return f

    mp.setattr(builtins, "open", g_open)
    mp.setattr(io, "open", g_io_open)
    mp.setattr(os, "open", g_os_open)
    for name in ("remove", "unlink", "rename", "replace", "utime", "chmod", "truncate", "mkdir", "rmdir"):
        mp.setattr(os, name, refuse(name))
    return attempts


def test_full_ingest_never_writes_to_the_library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"ro-{tmp_path.name}"
    shutil.copytree(FIX, root, ignore=shutil.ignore_patterns("manifest.json"))
    old = time.time() - 3600
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (old, old))
    before = snapshot(root)
    with pytest.MonkeyPatch.context() as mp:
        attempts = install_guard(mp)
        lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
        sweep_library(lib)
        WorkerProcess("w-ro").run(max_tasks=500)
        sweep_library(lib)  # and a rescan
    assert attempts == []
    assert snapshot(root) == before  # same names, contents, sizes and mtimes
    shutil.rmtree(root, ignore_errors=True)


def test_the_guard_itself_catches_writes(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"guard-{tmp_path.name}"
    root.mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        attempts = install_guard(mp)
        with pytest.raises(PermissionError):
            open(root / "x.fits", "wb")  # noqa: SIM115
        with pytest.raises(PermissionError):
            os.rename(root, root.with_name("elsewhere"))
        assert open(Path(settings.LIBRARY_ROOT).parent / "outside.txt", "w")  # noqa: SIM115  (outside: allowed)
    assert len(attempts) == 2
    shutil.rmtree(root, ignore_errors=True)
