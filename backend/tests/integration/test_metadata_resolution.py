"""T070, T071: quickstart V10. Stripped lights go to reconciliation; a NINA filename pattern fills them
"from filename pattern"; a bulk correction resolves the rest. Plus the metadata API contract."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import Dataset, Frame, MetadataSource, ReconciliationItem
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers"
STRIPPED = FIX / "stripped/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
NINA = "{date}_{time}_{filter}_{temp}_{exposure}s_{seq}"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"meta-{tmp_path.name}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    old = time.time() - 3600
    os.utime(dst, (old, old))


def run(root: Path) -> None:
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=200)


def test_v10_stripped_headers(library, admin_client):
    put(STRIPPED, library / "LIGHT" / STRIPPED.name)
    put(STRIPPED, library / "LIGHT" / "oddly named sub.xisf")  # same content: one frame
    run(library)
    frame = Frame.objects.get()
    assert frame.filter_norm is None and frame.exptime_s is None and frame.dataset is None
    r = admin_client.get("/api/v1/reconciliation")
    assert r.status_code == 200
    fields = {i["field"] for i in r.json() if i["kind"] == "missing_field"}
    assert fields == {"filter", "exptime"}

    # A NINA filename pattern fills both
    r = admin_client.post(
        "/api/v1/path-patterns", {"kind": "filename", "pattern": NINA}, content_type="application/json"
    )
    assert r.status_code == 201, r.content
    WorkerProcess("w-test").run(max_tasks=20)  # the re-resolve task
    frame.refresh_from_db()
    assert (frame.filter_norm, frame.exptime_s) == ("Hα", 600.0)
    fm = frame.metadata.get(field="filter", is_winner=True)
    assert fm.source == MetadataSource.FILENAME_PATTERN
    assert not ReconciliationItem.objects.filter(status="open").exists()
    assert Dataset.objects.get().sub_count == 1

    # Remove the pattern: back to reconciliation; then one bulk correction resolves it for good
    pid = r.json()["id"]
    assert admin_client.delete(f"/api/v1/path-patterns/{pid}").status_code == 204
    WorkerProcess("w-test").run(max_tasks=20)
    items = admin_client.get("/api/v1/reconciliation").json()
    filt = next(i for i in items if i["field"] == "filter")
    r = admin_client.post(
        f"/api/v1/reconciliation/{filt['id']}/resolve",
        {"value": "Ha", "apply_to_similar": True},
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["resolved"] == 1
    r = admin_client.post(
        "/api/v1/frames/metadata",
        {"sha256s": [frame.sha256], "field": "exptime", "value": 600},
        content_type="application/json",
    )
    assert r.json() == {"updated": 1}
    frame.refresh_from_db()
    assert (frame.filter_norm, frame.exptime_s) == ("Hα", 600.0)
    assert frame.metadata.get(field="filter", is_winner=True).source == MetadataSource.USER
    assert not ReconciliationItem.objects.filter(status="open").exists()


def test_reconciliation_groups_show_what_the_files_are(library, admin_client, django_assert_max_num_queries):
    """Each group says what its files are, by one example file; an ignore rule takes them off the list at once."""
    put(STRIPPED, library / "LIGHT" / "night 1" / STRIPPED.name)
    run(library)
    frame = Frame.objects.get()
    items = admin_client.get("/api/v1/reconciliation").json()
    assert {i["field"] for i in items} == {"filter", "exptime"}
    assert len({i["group"] for i in items}) == 2  # one group per field
    ex = next(i["example"] for i in items if i["field"] == "filter")
    assert ex["sha256"] == frame.sha256 and ex["frame_type"] == "light"
    assert ex["folder"] == "LIGHT/night 1" and ex["file_name"] == STRIPPED.name
    assert ex["library"] == library.name and ex["library_id"] is not None
    assert ex["needs"] == ["exptime", "filter"] and ex["filter"] is None and ex["exptime_s"] is None
    assert ex["width"] and ex["height"]

    # queries don't grow with the number of files
    with django_assert_max_num_queries(12):
        admin_client.get("/api/v1/reconciliation")

    r = admin_client.post(
        "/api/v1/ignore-rules",
        {"kind": "folder", "value": "LIGHT/night 1", "library_id": ex["library_id"]},
        content_type="application/json",
    )
    assert r.status_code == 201
    assert admin_client.get("/api/v1/reconciliation").json() == []  # before the worker has run
    WorkerProcess("w-test").run(max_tasks=20)
    assert admin_client.get("/api/v1/reconciliation").json() == []
    assert admin_client.get("/api/v1/reconciliation/counts").json() == {}
    assert admin_client.delete(f"/api/v1/ignore-rules/{r.json()['id']}").status_code == 204
    WorkerProcess("w-test").run(max_tasks=20)
    assert len(admin_client.get("/api/v1/reconciliation").json()) == 2  # undo brings them back


def test_pattern_validation_and_preview(library, admin_client, standard_client):
    put(
        FIX / "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
        library / "2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
    )
    run(library)
    bad = admin_client.post(
        "/api/v1/path-patterns", {"kind": "filename", "pattern": "{colour}"}, content_type="application/json"
    )
    assert bad.status_code == 422 and "isn't a field" in bad.json()["message"]
    assert (
        standard_client.post(
            "/api/v1/path-patterns", {"kind": "filename", "pattern": NINA}, content_type="application/json"
        ).status_code
        == 403
    )
    r = standard_client.post(
        "/api/v1/path-patterns/preview",
        {"pattern": {"kind": "folder", "pattern": "{date}/{type}/"}, "sample_paths": []},
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fields"] == ["frame_type"] and body["matching_files"] == 1
    assert body["samples"][0]["values"] == {"frame_type": "light"}
    r = standard_client.post(
        "/api/v1/path-patterns/preview",
        {
            "pattern": {"kind": "filename", "pattern": "{*}_{*}_{filter}_{*}"},
            "sample_paths": ["a_b_OIII_c.fits", "nope.fits"],
        },
        content_type="application/json",
    )
    assert [s["matched"] for s in r.json()["samples"]] == [True, False]
    assert r.json()["would_change"] == []  # the real file's filter is already Halpha
    r = standard_client.post(
        "/api/v1/path-patterns/preview",
        {"pattern": {"kind": "folder", "pattern": "{date}/{target}/"}},
        content_type="application/json",
    )
    assert r.json()["would_change"][0]["changes"] == [
        {"field": "target", "current": "NGC 7000", "new": "LIGHT"}
    ]


def test_classification_override_and_invalid_values(library, admin_client):
    put(
        FIX / "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
        library / "a.xisf",
    )
    run(library)
    sha = Frame.objects.get().sha256
    r = admin_client.post(
        "/api/v1/frames/classification",
        {"sha256s": [sha], "frame_type": "flat"},
        content_type="application/json",
    )
    assert r.json() == {"updated": 1}
    f = Frame.objects.get()
    assert (f.frame_type, f.classification_source) == ("flat", "user")
    assert f.dataset is None and Dataset.objects.get().sub_count == 0
    r = admin_client.post(
        "/api/v1/frames/metadata",
        {"sha256s": [sha], "field": "gain", "value": "lots"},
        content_type="application/json",
    )
    assert (
        r.status_code == 422 and "must be a number" in r.json()["message"] and "Gain" in r.json()["message"]
    )
    r = admin_client.post(
        "/api/v1/frames/classification",
        {"sha256s": [sha], "frame_type": "selfie"},
        content_type="application/json",
    )
    assert r.status_code == 422
    detail = admin_client.get(f"/api/v1/frames/{sha}").json()
    ft = next(m for m in detail["metadata"] if m["field"] == "frame_type" and m["is_winner"])
    assert ft["source"] == "user" and ft["set_by"] == "admin"
