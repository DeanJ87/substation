"""T088 (quickstart V12): ignore a frame and a folder; move the frame and copy the folder; neither is
processed; both are listed with an undo; undo processes them."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import Dataset, Frame, FrameStatus
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.models import Task
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture"
L0928 = FIX / "2026-09-28/LIGHT"
A = "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
B = "2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf"
C = "2026-09-29_02-03-37_Halpha_-19.90_600.00s_0002.xisf"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"ign-{tmp_path.name}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    old = time.time() - 3600
    os.utime(dst, (old, old))


def run(root: Path, tasks: int = 200) -> None:
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=tasks)


def hashes_for(name: str) -> int:
    return Task.objects.filter(name__endswith="hash_file", args__1__endswith=name).count()


def test_ignore_frame_and_folder_then_undo(library, admin_client):
    put(L0928 / A, library / "night" / A)
    put(L0928 / B, library / "night" / B)
    run(library)
    ds = Dataset.objects.get()
    assert ds.sub_count == 2
    sha_a = Frame.objects.get(copies__rel_path=f"night/{A}").sha256

    # Ignore one frame (content) and one folder
    r = admin_client.post(
        "/api/v1/ignore-rules",
        {"kind": "content", "value": sha_a, "note": "test shot"},
        content_type="application/json",
    )
    assert r.status_code == 201 and r.json()["matches"] == 1
    r = admin_client.post(
        "/api/v1/ignore-rules", {"kind": "folder", "value": "_old/"}, content_type="application/json"
    )
    assert r.status_code == 201
    folder_rule = r.json()["id"]
    WorkerProcess("w-test").run(max_tasks=20)
    assert Frame.objects.get(pk=sha_a).status == FrameStatus.IGNORED
    ds.refresh_from_db()
    assert ds.sub_count == 1

    # Move the ignored frame elsewhere, and put a new sub in the ignored folder
    os.rename(library / "night" / A, library / "moved.xisf")
    put(L0928 / C, library / "_old" / C)
    run(library)
    assert Frame.objects.get(pk=sha_a).status == FrameStatus.IGNORED  # still ignored at its new path
    assert hashes_for(C) == 0  # the ignored folder isn't even hashed
    assert Dataset.objects.get().sub_count == 1

    rules = admin_client.get("/api/v1/ignore-rules").json()
    assert {(x["kind"], x["matches"]) for x in rules} == {("content", 1), ("folder", 0)}

    # Undo both: the frame is back, and the folder's file is queued and processed
    for x in rules:
        assert admin_client.delete(f"/api/v1/ignore-rules/{x['id']}").status_code == 204
    WorkerProcess("w-test").run(max_tasks=20)
    assert Frame.objects.get(pk=sha_a).status == FrameStatus.CATALOGUED
    run(library)  # the rescan the undo requested
    assert hashes_for(C) == 1
    assert sum(Dataset.objects.values_list("sub_count", flat=True)) == 3  # C is another target
    assert folder_rule not in [x["id"] for x in admin_client.get("/api/v1/ignore-rules").json()]


def test_glob_rule_on_file_names_and_validation(library, standard_client):
    put(L0928 / A, library / "test_shot_001.xisf")
    put(L0928 / B, library / B)
    r = standard_client.post(
        "/api/v1/ignore-rules", {"kind": "glob", "value": "test_shot_*"}, content_type="application/json"
    )
    assert r.status_code == 201
    run(library)
    assert hashes_for("test_shot_001.xisf") == 0
    assert Frame.objects.count() == 1
    bad = standard_client.post(
        "/api/v1/ignore-rules", {"kind": "content", "value": "nope"}, content_type="application/json"
    )
    assert bad.status_code == 422 and "SHA-256" in bad.json()["message"]
    empty = standard_client.post(
        "/api/v1/ignore-rules", {"kind": "folder", "value": "/"}, content_type="application/json"
    )
    assert empty.status_code == 422


def test_frame_whose_every_copy_is_in_an_ignored_folder_is_ignored(library, admin_client):
    put(L0928 / A, library / "keep" / A)
    put(L0928 / B, library / "junk" / B)
    run(library)
    admin_client.post(
        "/api/v1/ignore-rules", {"kind": "folder", "value": "junk"}, content_type="application/json"
    )
    WorkerProcess("w-test").run(max_tasks=20)
    assert Frame.objects.get(copies__rel_path=f"junk/{B}").status == FrameStatus.IGNORED
    assert Frame.objects.get(copies__rel_path=f"keep/{A}").status == FrameStatus.CATALOGUED
    run(library)  # the ignored copy isn't reported missing
    assert not Frame.objects.filter(status=FrameStatus.MISSING).exists()
