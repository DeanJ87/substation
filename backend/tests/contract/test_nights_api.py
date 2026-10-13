"""T098: /datasets/{id}/nights and /nights/{date} (quickstart V13)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture"
FILES = [
    "2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
    "2026-09-28/LIGHT/2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf",
    "2026-09-28/LIGHT/BAD_2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf",
    "2026-09-28/FLAT/2026-09-29_05-02-35_Halpha_-20.10_2.00s_0000.xisf",
    "2026-10-07/LIGHT/2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf",
]

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ingested(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"n-{tmp_path.name}"
    for rel in FILES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIX / rel, dst)
        old = time.time() - 3600
        os.utime(dst, (old, old))
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w").run(max_tasks=100)
    yield
    shutil.rmtree(root, ignore_errors=True)


def test_dataset_nights(ingested, admin_client):
    ds = next(
        d for d in admin_client.get("/api/v1/datasets").json()["items"] if "Panel 2" in d["display_name"]
    )
    nights = admin_client.get(f"/api/v1/datasets/{ds['id']}/nights").json()
    assert [(n["night"], n["sub_count"], n["user_rejected_count"], n["integration_s"]) for n in nights] == [
        ("2026-09-28", 2, 1, 1200.0)
    ]


def test_night_page(ingested, admin_client):
    r = admin_client.get("/api/v1/nights/2026-09-28")
    assert r.status_code == 200
    n = r.json()
    assert [d["dataset"]["display_name"] for d in n["datasets"]] == ["NGC 7000 · Panel 2 · Hα"]
    assert [(c["type"], c["frame_count"]) for c in n["calibration_sets"]] == [("flat", 1)]
    assert n["previous"] is None and n["next"] == "2026-10-07"
    later = admin_client.get("/api/v1/nights/2026-10-07").json()
    assert later["previous"] == "2026-09-28" and later["datasets"][0]["sub_count"] == 1


def test_empty_night_is_404(ingested, admin_client):
    r = admin_client.get("/api/v1/nights/2026-01-01")
    assert r.status_code == 404 and "Nothing catalogued" in r.json()["message"]
