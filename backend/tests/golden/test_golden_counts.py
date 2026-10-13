"""T103 (quickstart V1, V2): a full ingest of the phase 2 spike tree, compared with the counts in
docs/spikes (SPIKE2_REPORT.md). Read-only: the write guard from test_read_only is on throughout, and every
file's name, size and mtime is unchanged afterwards.

    SUBSTATION_GOLDEN_DIR=/path/to/sub-test uv run pytest -m golden
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from apps.catalogue.models import (
    MASTER_TYPES,
    CalibrationSet,
    Dataset,
    Frame,
    FrameType,
    ReconciliationItem,
    UserVerdict,
)
from apps.ingest.sweep import sweep_library
from apps.libraries.models import Library
from substation.tasks.models import Task, TaskStatus
from substation.tasks.worker import WorkerProcess
from tests.integration.test_read_only import install_guard

GOLDEN = os.environ.get("SUBSTATION_GOLDEN_DIR")
pytestmark = [
    pytest.mark.golden,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(not GOLDEN, reason="set SUBSTATION_GOLDEN_DIR to the spike tree"),
]


def stats(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def ingest(root: Path, settings) -> None:  # noqa: ANN001
    settings.LIBRARY_ROOT = str(root.parent)
    settings.INGEST_VERIFY_COMPLETE = True
    lib = Library.objects.create(name="golden", mount_path=str(root))
    sweep_library(lib)
    workers = [
        threading.Thread(target=WorkerProcess(f"g{i}").run, kwargs={"max_tasks": 5000}) for i in range(4)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join()


def test_golden_counts(settings):
    root = Path(GOLDEN or "").resolve()
    before = stats(root)
    with pytest.MonkeyPatch.context() as mp:
        attempts = install_guard(mp)
        settings.LIBRARY_ROOT = str(root.parent)
        ingest(root, settings)
    assert attempts == [], attempts[:5]
    assert stats(root) == before  # V1: names, sizes and mtimes untouched

    assert Task.objects.filter(status=TaskStatus.FAILED).count() == 0
    frames = Frame.objects.all()
    assert frames.exclude(frame_type__in=MASTER_TYPES).count() == 636  # unique subs and calibration frames
    assert frames.filter(frame_type__in=MASTER_TYPES).count() == 36  # WBPP masters
    assert frames.filter(frame_type=FrameType.LIGHT).count() == 84
    assert UserVerdict.objects.count() == 18  # 17 BAD_ twins + 1 BAD_ without a twin
    assert ReconciliationItem.objects.filter(kind="bad_without_twin", status="open").count() == 1

    datasets = {d.display_name: (d.sub_count, d.user_rejected_count) for d in Dataset.objects.all()}
    assert len(datasets) == 8
    assert datasets["NGC 7000 · Panel 2 · Hα"] == (6, 2)
    assert datasets["NGC 7000 · Panel 3 · Hα"] == (24, 5)
    assert datasets["Heart Nebula · Panel 2 · Hα"] == (15, 4)
    assert datasets["Heart Nebula · Panel 2 · L"] == (1, 1)

    flats = {c.filter_norm: c.frame_count for c in CalibrationSet.objects.filter(type=FrameType.FLAT)}
    assert flats == {"L": 51, "R": 51, "G": 50, "SII": 50, "Hα": 50, "OIII": 50}
    dark_flats = sorted(
        (c.exptime_s, c.frame_count) for c in CalibrationSet.objects.filter(type=FrameType.DARK_FLAT)
    )
    assert dark_flats == [(0.01, 50), (1.0, 50), (2.0, 150)]
    assert not frames.filter(frame_type=FrameType.DARK).exists()  # every raw dark is a FlatWizard dark flat
