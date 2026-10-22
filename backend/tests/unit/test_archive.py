"""Archive collections (spec 013): library roles and who may take part, which files move, the move itself (copy,
verify, never overwrite, resume, cancel), scans during a move, suggestions, and the API."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.catalogue.models import (
    Change,
    Collection,
    CollectionMove,
    Copy,
    CopyEvent,
    Dataset,
    Frame,
    FrameStatus,
    FrameType,
    MoveItem,
    MoveItemState,
    MoveState,
)
from apps.catalogue.services import archive
from apps.libraries.models import Library
from apps.processing.models import CalibrationMatch, Master
from substation.tasks import Cancelled, Interrupted
from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 7, 21, tzinfo=UTC)


def libraries(tmp_path: Path) -> tuple[Library, Library]:
    roots = []
    for name in ("fast", "big"):
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / ".keep").write_text("")  # an empty folder reads as an unmounted share
        roots.append(tmp_path / name)
    archive_lib = Library.objects.create(name="big", mount_path=str(roots[1]), role="archive")
    active = Library.objects.create(
        name="fast", mount_path=str(roots[0]), role="active", archive_to=archive_lib
    )
    return active, archive_lib


def put(lib: Library, rel: str, content: bytes, frame_type: str = FrameType.LIGHT, **kw) -> Frame:
    p = Path(lib.mount_path) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    st = p.stat()
    f, _ = Frame.objects.get_or_create(
        sha256=hashlib.sha256(content).hexdigest(),
        defaults={
            "size_bytes": len(content),
            "format": "fits",
            "first_seen_at": T,
            "status": FrameStatus.CATALOGUED,
            "frame_type": frame_type,
            "date_obs_utc": T,
            **kw,
        },
    )
    Copy.objects.create(
        frame=f,
        library=lib,
        rel_path=rel,
        st_dev=st.st_dev,
        st_ino=st.st_ino,
        st_size=st.st_size,
        st_mtime_ns=st.st_mtime_ns,
        first_seen_at=T,
        last_seen_at=T,
    )
    return f


def collection(name: str, key: str) -> tuple[Collection, Dataset]:
    col = Collection.objects.create(name=name)
    ds = Dataset.objects.create(
        group_key=key, target=name, filter_norm="Ha", display_name=name, collection=col
    )
    return col, ds


@pytest.fixture
def setup(tmp_path):
    """M 31 has two lights and a master flat only it uses; M 33 (also in the active library) shares the master dark."""
    active, big = libraries(tmp_path)
    col, ds = collection("M 31", "m31")
    other, ods = collection("M 33", "m33")
    lights = [
        put(active, f"M 31/2026-03-07/Light_{i}.fits", f"m31 light {i}".encode(), dataset=ds) for i in (1, 2)
    ]
    flat = put(active, "Calibration/MasterFlat_Ha.xisf", b"master flat", FrameType.MASTER_FLAT)
    dark = put(active, "Calibration/MasterDark_300.xisf", b"master dark", FrameType.MASTER_DARK)
    for f in lights:
        CalibrationMatch.objects.create(frame=f, state="matched", dark=dark, flat=flat)
    o = put(active, "M 33/Light_1.fits", b"m33 light", dataset=ods)
    CalibrationMatch.objects.create(frame=o, state="matched", dark=dark)
    return {
        "active": active,
        "big": big,
        "col": col,
        "lights": lights,
        "flat": flat,
        "dark": dark,
        "other": other,
    }


def run(col: Collection, direction: str = "archive") -> CollectionMove:
    move, _ = archive.start_move(col, direction)
    archive.run_move(move.pk)
    move.refresh_from_db()
    return move


# -- roles and who may take part --------------------------------------------------------------------------------


def read_only(monkeypatch, *libs: Library) -> None:
    paths = {lib.mount_path for lib in libs}
    real = os.access
    monkeypatch.setattr(os, "access", lambda p, m: False if str(p) in paths else real(p, m))


def test_a_read_only_library_cant_take_a_role_or_allow_deleting(
    tmp_path, admin_client, monkeypatch, settings
):
    settings.LIBRARY_NAMES = "organised,archive,active"
    lib = Library.objects.create(name="archive", mount_path=str(tmp_path))
    read_only(monkeypatch, lib)
    listed = admin_client.get("/api/v1/libraries").json()[0]
    assert listed["writable"] is False
    assert listed["read_only_reason"] == (
        "Mounted read-only. Mount it read-write (SUBSTATION_LIBRARY_2_MODE=rw) to allow this."
    )
    for body in ({"role": "archive"}, {"allow_delete": True}):
        r = admin_client.patch(f"/api/v1/libraries/{lib.pk}", body, content_type="application/json")
        assert r.status_code == 422 and "SUBSTATION_LIBRARY_2_MODE=rw" in r.json()["message"]
    assert archive.read_only_reason(lib) is not None


def test_the_reason_names_the_first_slot_and_unknown_libraries_generically(tmp_path, monkeypatch, settings):
    settings.LIBRARY_NAMES = "organised,.no-library,.no-library-3"
    first = Library.objects.create(name="organised", mount_path=str(tmp_path / "a"))
    extra = Library.objects.create(name="extra", mount_path=str(tmp_path / "b"))
    read_only(monkeypatch, first, extra)
    assert "SUBSTATION_LIBRARY_MODE=rw" in (archive.read_only_reason(first) or "")
    assert "its volume line ending :rw" in (archive.read_only_reason(extra) or "")


def test_roles_and_the_archive_target(tmp_path, admin_client):
    a = Library.objects.create(name="a", mount_path=str(tmp_path))
    b = Library.objects.create(name="b", mount_path=str(tmp_path))

    def patch(lib: Library, body: dict):
        return admin_client.patch(f"/api/v1/libraries/{lib.pk}", body, content_type="application/json")

    assert patch(a, {"archive_to": b.pk}).status_code == 422  # a isn't active yet
    assert patch(a, {"role": "active"}).json()["role"] == "active"
    assert patch(a, {"archive_to": b.pk}).status_code == 422  # b isn't an archive yet
    assert patch(b, {"role": "archive"}).status_code == 200
    assert patch(a, {"archive_to": b.pk}).json()["archive_to"] == b.pk
    assert patch(b, {"role": ""}).json()["role"] == ""  # no longer an archive: a stops pointing at it
    a.refresh_from_db()
    assert a.archive_to_id is None


def test_a_standard_user_cant_change_roles(tmp_path, standard_client):
    a = Library.objects.create(name="a", mount_path=str(tmp_path))
    r = standard_client.patch(
        f"/api/v1/libraries/{a.pk}", {"role": "active"}, content_type="application/json"
    )
    assert r.status_code == 403


# -- which files move ------------------------------------------------------------------------------------------


def test_the_plan_moves_lights_and_calibration_only_this_collection_uses(setup):
    p = archive.plan(setup["col"], "archive")
    assert {r[1] for r in p.lights} == {"M 31/2026-03-07/Light_1.fits", "M 31/2026-03-07/Light_2.fits"}
    assert [r[1] for r in p.calibration] == ["Calibration/MasterFlat_Ha.xisf"]
    assert p.kept == 1  # the master dark: M 33 is still in the active library
    assert p.files == 3 and p.bytes == sum(len(f"m31 light {i}") for i in (1, 2)) + len("master flat")


# -- the move ---------------------------------------------------------------------------------------------------


def test_archive_moves_every_file_to_the_same_path_and_bring_back_returns_them(setup):
    active, big, col = setup["active"], setup["big"], setup["col"]
    before = Frame.objects.count(), Copy.objects.count()
    move = run(col)
    assert move.state == MoveState.DONE and move.files_done == 3 and move.problems == 0
    for f in [*setup["lights"], setup["flat"]]:
        c = Copy.objects.get(frame=f)
        assert c.library == big and (Path(big.mount_path) / c.rel_path).read_bytes()
        assert not (Path(active.mount_path) / c.rel_path).exists()
    assert Copy.objects.get(frame=setup["dark"]).library == active  # still used by M 33
    assert (Frame.objects.count(), Copy.objects.count()) == before  # nothing lost or duplicated (SC-001)
    assert CopyEvent.objects.filter(kind="moved", details__by="archive").count() == 3
    assert archive.where(col).location == "archive"
    assert not list(Path(big.mount_path).rglob("*.substation-part"))

    back = run(col, "bring_back")
    assert back.state == MoveState.DONE and back.files_done == 3
    assert archive.where(col).location == "active"
    assert Copy.objects.filter(library=big).count() == 0


def test_a_different_file_at_the_destination_is_never_overwritten(setup):
    big = setup["big"]
    clash = Path(big.mount_path) / "M 31/2026-03-07/Light_1.fits"
    clash.parent.mkdir(parents=True)
    clash.write_bytes(b"something else")
    move = run(setup["col"])
    assert move.files_done == 2 and move.problems == 1
    item = MoveItem.objects.get(move=move, state=MoveItemState.PROBLEM)
    assert "A different file is already at" in item.reason
    assert clash.read_bytes() == b"something else"
    assert (Path(setup["active"].mount_path) / item.rel_path).exists()  # the original stays


def test_the_same_file_at_the_destination_is_not_copied_again(setup, monkeypatch):
    big = setup["big"]
    same = Path(big.mount_path) / "M 31/2026-03-07/Light_1.fits"
    same.parent.mkdir(parents=True)
    same.write_bytes(b"m31 light 1")
    copied: list[Path] = []
    real = archive._copy

    def counting(m, s, p):  # noqa: ANN001
        copied.append(s)
        real(m, s, p)

    monkeypatch.setattr(archive, "_copy", counting)
    move = run(setup["col"])
    assert move.files_done == 3 and len(copied) == 2
    assert not (Path(setup["active"].mount_path) / "M 31/2026-03-07/Light_1.fits").exists()


def test_a_file_whose_content_changed_stays_where_it_was(setup):
    src = Path(setup["active"].mount_path) / "M 31/2026-03-07/Light_2.fits"
    src.write_bytes(b"not what was catalogued")
    move = run(setup["col"])
    item = MoveItem.objects.get(move=move, state=MoveItemState.PROBLEM)
    assert item.rel_path.endswith("Light_2.fits") and "didn't match" in item.reason
    assert src.exists() and not (Path(setup["big"].mount_path) / item.rel_path).exists()


def test_a_move_interrupted_by_a_restart_carries_on(setup, monkeypatch):
    real = archive._copy
    calls = {"n": 0}

    def stop_on_second(m, s, p):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 2:
            p.write_bytes(b"half")  # a half-written copy
            raise Interrupted("The worker stopped; back in the queue.")
        return real(m, s, p)

    monkeypatch.setattr(archive, "_copy", stop_on_second)
    move, _ = archive.start_move(setup["col"], "archive")
    with pytest.raises(Interrupted):
        archive.run_move(move.pk)
    move.refresh_from_db()
    assert move.state == MoveState.RUNNING and move.files_done == 1
    assert not list(Path(setup["big"].mount_path).rglob("*.substation-part"))  # never left half-copied
    archive.run_move(move.pk)  # the worker picks the job up again
    move.refresh_from_db()
    assert move.state == MoveState.DONE and move.files_done == 3 and move.problems == 0
    assert archive.where(setup["col"]).location == "archive"


def test_a_cancelled_move_leaves_each_file_moved_or_untouched(setup, monkeypatch):
    real = archive._copy
    calls = {"n": 0}

    def cancel_on_second(m, s, p):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 2:
            p.write_bytes(b"half")
            raise Cancelled("Cancelled while running.")
        return real(m, s, p)

    monkeypatch.setattr(archive, "_copy", cancel_on_second)
    move, _ = archive.start_move(setup["col"], "archive")
    with pytest.raises(Cancelled):
        archive.run_move(move.pk)
    move.refresh_from_db()
    assert move.state == MoveState.CANCELLED and move.files_done == 1
    w = archive.where(setup["col"])
    assert w.location == "both"
    for c in Copy.objects.filter(frame__in=setup["lights"]):
        assert (Path(c.library.mount_path) / c.rel_path).exists()
        other = setup["active"] if c.library == setup["big"] else setup["big"]
        assert not (Path(other.mount_path) / c.rel_path).exists()
    assert not list(Path(setup["big"].mount_path).rglob("*.substation-part"))


def test_cancelling_a_waiting_move(setup):
    move, _ = archive.start_move(setup["col"], "archive")
    archive.cancel_move(move, "owner")
    assert move.state == MoveState.CANCELLED
    assert Task.objects.get(pk=str(move.task_id)).status == TaskStatus.CANCELLED
    with pytest.raises(archive.CantMove):
        archive.cancel_move(move)


def test_a_move_refuses_read_only_libraries(setup, monkeypatch):
    read_only(monkeypatch, setup["big"])
    with pytest.raises(archive.CantMove, match="big: Mounted read-only"):
        archive.plan(setup["col"], "archive")


def test_a_move_queued_before_a_library_went_read_only_fails_with_the_reason(setup, monkeypatch):
    move, _ = archive.start_move(setup["col"], "archive")
    read_only(monkeypatch, setup["active"])
    assert archive.run_move(move.pk)["result"] == "failed"
    move.refresh_from_db()
    assert move.state == MoveState.FAILED and "Mounted read-only" in move.error


def test_scans_during_a_move_dont_report_its_files_missing(setup):
    from apps.ingest.sweep import sweep_library

    move, _ = archive.start_move(setup["col"], "archive")
    archive._plan_items(move)
    # the copy of Light_1 is half-way: gone from the active library, not yet recorded in the archive
    (Path(setup["active"].mount_path) / "M 31/2026-03-07/Light_1.fits").unlink()
    result = sweep_library(setup["active"])
    assert result.complete and result.missing == 0
    assert Copy.objects.get(frame=setup["lights"][0]).present


def test_a_second_move_waits_for_the_first(setup):
    from substation.tasks import Reschedule

    first, _ = archive.start_move(setup["col"], "archive")
    second = CollectionMove.objects.create(
        collection=setup["col"], direction="bring_back", from_library=setup["big"], to_library=setup["active"]
    )
    with pytest.raises(Reschedule):
        archive.run_move(second.pk)
    with pytest.raises(archive.CantMove, match="already being moved"):
        archive.start_move(setup["col"], "archive")
    assert first.state == MoveState.QUEUED


# -- suggestions --------------------------------------------------------------------------------------------------


def test_suggestions_need_old_subs_and_a_current_master_and_can_be_dismissed(setup):
    col = setup["col"]
    assert archive.suggested() == set()  # no current master yet
    Master.objects.create(dataset=Dataset.objects.get(collection=col), version=1, state="current")
    assert archive.suggested() == {col.pk}  # its subs are from March
    Frame.objects.filter(pk=setup["lights"][0].pk).update(date_obs_utc=timezone.now() - timedelta(days=5))
    assert archive.suggested() == set()  # shot recently
    Frame.objects.filter(pk=setup["lights"][0].pk).update(date_obs_utc=T)
    Collection.objects.filter(pk=col.pk).update(archive_dismissed_at=timezone.now())
    assert archive.suggested() == set()


def test_a_collection_whose_projects_are_all_done_is_suggested_at_once(setup):
    from apps.catalogue.models import Project

    col = setup["col"]
    Frame.objects.filter(pk__in=[f.pk for f in setup["lights"]]).update(date_obs_utc=timezone.now())
    a = Project.objects.create(collection=col, season="2026")
    Project.objects.create(collection=col, season="2025", done_at=timezone.now())
    assert archive.suggested() == set()  # shot yesterday, no master, one project still going
    Project.objects.filter(pk=a.pk).update(done_at=timezone.now())
    assert archive.suggested() == {col.pk}  # every project done: no need to wait
    move = CollectionMove.objects.create(
        collection=col, direction="archive", from_library=setup["active"], to_library=setup["big"]
    )
    assert archive.suggested() == set()  # moving now
    move.state = MoveState.DONE
    move.save()
    Collection.objects.filter(pk=col.pk).update(archive_dismissed_at=timezone.now())
    assert archive.suggested() == set()  # dismissed
    Collection.objects.filter(pk=col.pk).update(archive_dismissed_at=None)
    Copy.objects.filter(frame__dataset__collection=col).update(library=setup["big"])
    assert archive.suggested() == set()  # its files are in the archive already


# -- API -------------------------------------------------------------------------------------------------------


def test_the_api_previews_starts_follows_and_undoes_a_move(setup, admin_client):
    col = setup["col"]
    files = admin_client.get(f"/api/v1/collections/{col.pk}/files").json()
    assert files["location"] == "active" and files["archive"]["possible"] is True
    assert files["archive"]["to_library"] == "big" and files["bring_back"]["possible"] is False
    preview = admin_client.get(f"/api/v1/collections/{col.pk}/move-preview?direction=archive").json()
    assert preview == {
        "direction": "archive",
        "from_library": "fast",
        "to_library": "big",
        "files": 3,
        "bytes": preview["bytes"],
        "lights": 2,
        "calibration": 1,
        "calibration_kept": 1,
    }
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/move", {"direction": "archive"}, content_type="application/json"
    )
    assert r.status_code == 202 and r.json()["state"] == "queued" and r.json()["change_id"]
    assert Change.objects.get(pk=r.json()["change_id"]).summary.startswith("Archived M 31: 3 files")
    again = admin_client.post(
        f"/api/v1/collections/{col.pk}/move", {"direction": "archive"}, content_type="application/json"
    )
    assert again.status_code == 409 and "already being moved" in again.json()["message"]
    assert admin_client.get(f"/api/v1/collections/{col.pk}/files").json()["move"]["state"] == "queued"
    undone = admin_client.post(f"/api/v1/changes/{r.json()['change_id']}/undo")
    assert undone.status_code == 200 and "Cancelled the move before it started" in undone.json()["note"]
    assert CollectionMove.objects.get(pk=r.json()["id"]).state == MoveState.CANCELLED


def test_undoing_a_finished_archive_brings_the_files_back(setup, admin_client):
    col = setup["col"]
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/move", {"direction": "archive"}, content_type="application/json"
    )
    archive.run_move(r.json()["id"])
    undone = admin_client.post(f"/api/v1/changes/{r.json()['change_id']}/undo").json()
    assert "back to fast" in undone["note"]
    back = CollectionMove.objects.exclude(pk=r.json()["id"]).get()
    archive.run_move(back.pk)
    assert archive.where(col).location == "active"


def test_the_api_says_why_a_move_cant_happen(setup, admin_client, monkeypatch):
    col = setup["col"]
    read_only(monkeypatch, setup["big"])
    files = admin_client.get(f"/api/v1/collections/{col.pk}/files").json()
    assert files["archive"]["possible"] is False and "Mounted read-only" in files["archive"]["reason"]
    r = admin_client.get(f"/api/v1/collections/{col.pk}/move-preview?direction=archive")
    assert r.status_code == 409 and "Mount it read-write" in r.json()["message"]


def test_read_only_accounts_cant_move_or_dismiss(setup, django_user_model):
    from django.contrib.auth.models import Group

    from apps.accounts.roles import VIEWER, ensure_groups
    from tests.conftest import signed_in_client

    ensure_groups()
    u = django_user_model.objects.create_user(username="viewer", password="correct-horse-battery")
    u.groups.add(Group.objects.get(name=VIEWER))
    c = signed_in_client("viewer")
    col = setup["col"]
    assert c.get(f"/api/v1/collections/{col.pk}/files").json()["can_move"] is False
    r = c.post(
        f"/api/v1/collections/{col.pk}/move", {"direction": "archive"}, content_type="application/json"
    )
    assert r.status_code == 403
    assert c.post(f"/api/v1/collections/{col.pk}/archive-suggestion/dismiss").status_code == 403


def test_cancel_and_dismiss_through_the_api(setup, admin_client):
    col = setup["col"]
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/move", {"direction": "archive"}, content_type="application/json"
    )
    c = admin_client.post(f"/api/v1/moves/{r.json()['id']}/cancel")
    assert c.status_code == 200 and c.json()["state"] == "cancelled"
    assert admin_client.post(f"/api/v1/moves/{r.json()['id']}/cancel").status_code == 409
    assert admin_client.post(f"/api/v1/collections/{col.pk}/archive-suggestion/dismiss").status_code == 204
    col.refresh_from_db()
    assert col.archive_dismissed_at is not None


def test_the_library_lists_where_each_collection_is(setup, admin_client):
    run(setup["col"])
    cards = {c["name"]: c for c in admin_client.get("/api/v1/library").json()["collections"]}
    assert cards["M 31"]["files_where"] == "archive" and cards["M 33"]["files_where"] == "active"


def test_activity_names_the_move(setup):
    from substation.tasks.activity import _target, outcome

    move, _ = archive.start_move(setup["col"], "archive")
    t = Task.objects.get(pk=str(move.task_id))
    assert _target(t)[0] == "Archive · M 31 · fast → big"
    assert outcome("move_collection", {"result": "done", "files": 3, "problems": 1}, "x") == (
        "Moved 3 files · x; 1 left where they were"
    )


def test_the_suggestion_setting_is_checked(admin_client):
    r = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"archive": {"suggest_after_days": -1}}},
        content_type="application/json",
    )
    assert r.status_code == 422
    r = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"archive": {"suggest_after_days": 90}}},
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["processing"]["archive"]["suggest_after_days"] == 90
