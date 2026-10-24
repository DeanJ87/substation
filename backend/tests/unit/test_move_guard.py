"""A collection's builds and its file moves take turns (spec 013, amendment 2026-10-24): a move, archive,
bring-back or bin is refused while a stack, stitch, post-processing, progression or calibration build reads the
files, and a build waits while the files move."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.catalogue.models import CollectionMove, FrameType, MoveState
from apps.catalogue.services import archive, binning
from apps.finished.models import Progression, ProgressionState
from apps.processing.models import BuiltMaster, CombinedMaster, Master, MasterState
from apps.processing.move_guard import builds, check_collection
from substation.tasks import Reschedule
from substation.tasks.models import Task, TaskStatus
from tests.unit.test_archive import collection, libraries, put

pytestmark = pytest.mark.django_db


def task(status: str = TaskStatus.RUNNING, name: str = "x", **kw) -> Task:
    now = timezone.now()
    return Task.objects.create(name=name, status=status, run_after=now, enqueued_at=now, **kw)


@pytest.fixture
def ngc(tmp_path: Path):
    active, big = libraries(tmp_path)
    col, ds = collection("NGC 7000", "ngc7000")
    lights = [put(active, f"NGC 7000/Light_{i}.fits", f"ngc light {i}".encode(), dataset=ds) for i in (1, 2)]
    other, ods = collection("M 31", "m31")
    put(active, "M 31/Light_1.fits", b"m31 light", dataset=ods)
    return {"col": col, "ds": ds, "lights": lights, "other": other, "ods": ods, "active": active}


def stacking(ds, status: str = TaskStatus.RUNNING, version: int = 3) -> Master:  # noqa: ANN001
    state = MasterState.RUNNING if status == TaskStatus.RUNNING else MasterState.QUEUED
    return Master.objects.create(dataset=ds, version=version, state=state, task=task(status))


# -- moves refused while a build reads the files -----------------------------------------------------------------


def test_a_running_stack_refuses_archiving_with_a_plain_reason(ngc, admin_client):
    stacking(ngc["ds"])
    why = "NGC 7000's Ha master v3 is being stacked; try again when it finishes."
    with pytest.raises(archive.CantMove, match="being stacked") as e:
        archive.start_move(ngc["col"], "archive")
    assert str(e.value) == why
    assert not CollectionMove.objects.exists()
    r = admin_client.post(
        f"/api/v1/collections/{ngc['col'].pk}/move", {"direction": "archive"}, "application/json"
    )
    assert r.status_code == 409 and r.json()["message"] == why
    # shown before trying: the Files panel's choice and the confirm's preview say so
    files = admin_client.get(f"/api/v1/collections/{ngc['col'].pk}/files").json()
    assert files["archive"] == {"possible": False, "reason": why, "from_library": None, "to_library": None}
    preview = admin_client.get(f"/api/v1/collections/{ngc['col'].pk}/move-preview?direction=archive").json()
    assert preview["refused"] == why and preview["files"] == 2


def test_a_queued_stack_refuses_too_and_a_finished_one_does_not(ngc):
    m = stacking(ngc["ds"], TaskStatus.READY)
    assert (
        check_collection(ngc["col"])
        == "NGC 7000's Ha master v3 is waiting to be stacked; try again when it finishes."
    )
    # its job ended without it (cancelled in Activity): the master's stale state doesn't hold the files
    Task.objects.filter(pk=str(m.task_id)).update(status=TaskStatus.CANCELLED)
    assert check_collection(ngc["col"]) == ""
    move, _ = archive.start_move(ngc["col"], "archive")
    assert move.state == MoveState.QUEUED


def test_another_collections_build_doesnt_stop_it(ngc):
    stacking(ngc["ods"])
    assert check_collection(ngc["col"]) == ""
    assert "M 31's Ha master v3 is being stacked" in check_collection(ngc["other"])


def test_stitching_post_processing_and_progressions_refuse(ngc):
    ref = Master.objects.create(dataset=ngc["ds"], version=1, state=MasterState.CURRENT)
    CombinedMaster.objects.create(
        collection=ngc["col"],
        filter_norm="Hα",
        version=1,
        method=CombinedMaster.Method.STITCH,
        state=MasterState.RUNNING,
        reference=ref,
        task=task(),
    )
    task(TaskStatus.READY, dedupe_key=f"post:{ref.pk}")
    from apps.catalogue.models import Project
    from apps.finished.models import FinishedProject
    from apps.libraries.models import Library

    lib = Library.objects.create(name="completed", mount_path="/nowhere", role="completed")
    fp = FinishedProject.objects.create(
        library=lib, rel_path="x", kind="astro", subject="NGC 7000", name="Wall"
    )
    fp.linked_projects.set([Project.objects.create(collection=ngc["col"])])
    Progression.objects.create(project=fp, state=ProgressionState.RUNNING, task=task())
    found = builds(ngc["col"])
    assert found == [
        "NGC 7000's Hα mosaic is being stitched",
        "NGC 7000's Ha master v1 is waiting to be post-processed",
        "The progression of Wall is being built",
    ]
    assert check_collection(ngc["col"]) == (
        "NGC 7000's Hα mosaic is being stitched (and 2 more jobs); try again when they finish."
    )


def test_a_calibration_master_its_subs_use_refuses(ngc):
    from apps.catalogue.models import CalibrationSet
    from apps.processing.models import CalibrationMatch

    now = timezone.now()
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT, filter_norm="Ha", exptime_s=2, session_start_utc=now, session_end_utc=now
    )
    raw = put(ngc["active"], "Calibration/Flat_1.fits", b"raw flat", FrameType.FLAT, calibration_set=cs)
    master = put(ngc["active"], "Calibration/MasterFlat.fits", b"master flat", FrameType.MASTER_FLAT)
    for f in ngc["lights"]:
        CalibrationMatch.objects.create(frame=f, state="matched", flat=master)
    bm = BuiltMaster.objects.create(calibration_set=cs, frame=master, state="queued")
    task(TaskStatus.READY, name="apps.processing.calibration.build_master", args=[bm.pk])
    assert raw.calibration_set_id == cs.pk
    assert builds(ngc["col"]) == ["A master flat (Ha) that NGC 7000's subs use is waiting to be built"]
    assert builds(ngc["other"]) == []


def test_binning_its_subs_is_refused_and_the_daily_tidy_leaves_them(ngc, admin_client):
    stacking(ngc["ds"])
    sha = ngc["lights"][0].pk
    r = admin_client.post("/api/v1/bin", {"sha256s": [sha]}, "application/json")
    assert r.status_code == 409 and "being stacked" in r.json()["message"]
    from apps.processing.models import MachineGrade

    MachineGrade.objects.create(frame=ngc["lights"][0], verdict="reject", weight=0, reason="trailed")
    MachineGrade.objects.filter(frame=ngc["lights"][0]).update(graded_at=timezone.now() - timedelta(days=90))
    assert binning.auto_bin()["binned"] == 0


def test_undoing_a_move_isnt_held_by_builds_waiting_for_it(ngc):
    move, _ = archive.start_move(ngc["col"], "archive")
    Task.objects.filter(pk=str(move.task_id)).update(status=TaskStatus.RUNNING)
    CollectionMove.objects.filter(pk=move.pk).update(state=MoveState.RUNNING)
    stacking(ngc["ds"], TaskStatus.READY)  # started during the move: it waits for it
    archive.undo(move.pk)  # the move back is queued behind it
    assert CollectionMove.objects.filter(collection=ngc["col"]).count() == 2


def test_a_move_waits_for_a_build_that_started_just_before_it(ngc):
    move, _ = archive.start_move(ngc["col"], "archive")
    stacking(ngc["ds"])  # slipped in between the check and the job
    with pytest.raises(Reschedule, match="Waiting: NGC 7000's Ha master v3 is being stacked"):
        archive.run_move(move.pk)


# -- builds wait while the files move -----------------------------------------------------------------------------


def moving(col) -> CollectionMove:  # noqa: ANN001
    move, _ = archive.start_move(col, "archive")
    return move


def test_a_stack_waits_while_its_collections_files_move(ngc):
    from apps.processing.masters import integrate

    moving(ngc["col"])
    m = Master.objects.create(dataset=ngc["ds"], version=4, state=MasterState.QUEUED)
    with pytest.raises(Reschedule) as e:
        integrate.call(m.pk)
    note = "Waiting for NGC 7000's files to be archived; starts when the move finishes."
    assert e.value.note == note
    m.refresh_from_db()
    assert m.state == MasterState.QUEUED and m.state_reason == note


def test_stitching_post_processing_and_progressions_wait_too(ngc):
    from apps.finished.progression import build_progression
    from apps.processing.combine import stitch_mosaic
    from apps.processing.postprocess import postprocess_master

    moving(ngc["col"])
    ref = Master.objects.create(dataset=ngc["ds"], version=1, state=MasterState.CURRENT, output_path="/x.fit")
    cm = CombinedMaster.objects.create(
        collection=ngc["col"], filter_norm="Hα", version=1, method="stitch", reference=ref
    )
    with pytest.raises(Reschedule, match="to be archived"):
        stitch_mosaic.call(ngc["col"].pk, [cm.pk])
    cm.refresh_from_db()
    assert cm.state == MasterState.QUEUED and "to be archived" in cm.state_reason
    with pytest.raises(Reschedule, match="to be archived"):
        postprocess_master.call(ref.pk)

    from apps.catalogue.models import Project
    from apps.finished.models import FinishedProject
    from apps.libraries.models import Library

    lib = Library.objects.create(name="completed", mount_path="/nowhere", role="completed")
    fp = FinishedProject.objects.create(
        library=lib, rel_path="x", kind="astro", subject="NGC 7000", name="Wall"
    )
    fp.linked_projects.set([Project.objects.create(collection=ngc["col"])])
    with pytest.raises(Reschedule, match="to be archived"):
        build_progression.call(fp.pk)
    prog = Progression.objects.get(project=fp)
    assert prog.state == ProgressionState.QUEUED and "to be archived" in prog.reason


def test_another_collections_move_doesnt_hold_a_stack(ngc):
    from apps.processing.move_guard import wait_for_moves

    moving(ngc["other"])
    wait_for_moves([ngc["col"].pk])  # nothing raised
    with pytest.raises(Reschedule):
        wait_for_moves([ngc["other"].pk])


def test_a_calibration_master_waits_while_its_frames_move_with_a_collection(ngc):
    from apps.catalogue.models import CalibrationSet
    from apps.processing.calibration import build_master
    from apps.processing.models import CalibrationMatch

    now = timezone.now()
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT, filter_norm="Ha", exptime_s=2, session_start_utc=now, session_end_utc=now
    )
    put(ngc["active"], "Calibration/Flat_1.fits", b"raw flat", FrameType.FLAT, calibration_set=cs)
    master = put(ngc["active"], "Calibration/MasterFlat.fits", b"master flat", FrameType.MASTER_FLAT)
    for f in ngc["lights"]:
        CalibrationMatch.objects.create(frame=f, state="matched", flat=master)
    bm = BuiltMaster.objects.create(calibration_set=cs, frame=master, state="queued")
    moving(ngc["other"])  # another collection's move: no wait
    moving(ngc["col"])
    with pytest.raises(Reschedule, match="NGC 7000's files to be archived"):
        build_master.call(bm.pk)
    bm.refresh_from_db()
    assert bm.state == "queued"
