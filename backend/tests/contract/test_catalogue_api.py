"""T047: read endpoints for libraries, datasets and frames (contracts/openapi.yaml)."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "headers/capture"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def catalogued(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"lib-{tmp_path.name}"
    for f in (FIX / "2026-09-28/LIGHT").glob("*.xisf"):
        if f.name.startswith("._"):
            continue
        dst = root / "2026-09-28" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
        os.utime(dst, (time.time() - 3600,) * 2)
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=100)
    yield lib
    shutil.rmtree(root, ignore_errors=True)


def test_libraries(admin_client, catalogued):
    r = admin_client.get("/api/v1/libraries")
    assert r.status_code == 200
    lib = next(x for x in r.json() if x["name"] == catalogued.name)
    assert lib["status"] == "ok" and lib["frame_count"] >= 4 and lib["mount_path"].endswith(catalogued.name)


def test_libraries_patch_is_admin_only(admin_client, standard_client, catalogued):
    body = json.dumps({"enabled": False, "site": {"name": "Home", "lat": 54.99, "lon": -1.66}})
    r = standard_client.patch(
        f"/api/v1/libraries/{catalogued.id}", data=body, content_type="application/json"
    )
    assert r.status_code == 403
    r = admin_client.patch(f"/api/v1/libraries/{catalogued.id}", data=body, content_type="application/json")
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["site"]["lon"] == -1.66


def test_rescan(admin_client, catalogued):
    r = admin_client.post(f"/api/v1/libraries/{catalogued.id}/rescan")
    assert r.status_code == 202


def test_datasets_list_and_detail(admin_client, catalogued):
    r = admin_client.get("/api/v1/datasets")
    assert r.status_code == 200
    items = r.json()["items"]
    names = {d["display_name"] for d in items}
    assert {"NGC 7000 · Panel 2 · Hα", "Heart Nebula · Panel 2 · Hα"} <= names
    d = next(x for x in items if x["display_name"] == "NGC 7000 · Panel 2 · Hα")
    assert d["state"] in ("ok", "needs_reconciliation") and d["sub_count"] >= 1
    assert d["last_night"] == "2026-09-28"
    r = admin_client.get(f"/api/v1/datasets/{d['id']}")
    assert r.status_code == 200 and r.json()["id"] == d["id"]
    assert admin_client.get("/api/v1/datasets/999999").status_code == 404


def test_frames_list_filters_and_pagination(admin_client, catalogued):
    r = admin_client.get("/api/v1/frames?type=light&limit=2")
    body = r.json()
    assert r.status_code == 200 and len(body["items"]) == 2 and body["next_cursor"]
    r2 = admin_client.get(f"/api/v1/frames?type=light&limit=2&cursor={body['next_cursor']}")
    seen = {f["sha256"] for f in body["items"]} | {f["sha256"] for f in r2.json()["items"]}
    assert len(seen) == len(body["items"]) + len(r2.json()["items"])
    r = admin_client.get("/api/v1/frames?q=Panel%202&night=2026-09-28")
    assert all(f["night"] == "2026-09-28" for f in r.json()["items"])


def test_frame_detail(admin_client, catalogued):
    sha = admin_client.get("/api/v1/frames?type=light&limit=1").json()["items"][0]["sha256"]
    r = admin_client.get(f"/api/v1/frames/{sha}")
    assert r.status_code == 200
    f = r.json()
    assert f["sha256"] == sha and f["copy_list"] and f["headers"] and f["metadata"]
    filt = next(m for m in f["metadata"] if m["field"] == "filter")
    assert filt["source"] == "header" and filt["source_detail"] == "FILTER"
    assert admin_client.get("/api/v1/frames/" + "0" * 64).status_code == 404


def test_requires_sign_in(catalogued):
    assert Client().get("/api/v1/datasets").status_code == 401
