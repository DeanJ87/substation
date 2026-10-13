"""The bin (spec 011): a binned file moves to its library's quarantine (or is only hidden where SubStation may not
delete), comes back on restore, and is deleted for good after its purge date; long-rejected subs bin themselves.
The frame's record always stays."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.catalogue.models import Copy, Frame, FrameStatus, FrameType
from apps.catalogue.services.binning import QUARANTINE, auto_bin, bin_frames, purge_due, restore_frames
from apps.libraries.models import Library
from apps.processing.models import MachineGrade

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 7, 21, tzinfo=UTC)


def sub(tmp_path, name: str, allow: bool = True) -> tuple[Frame, Library]:
    lib, _ = Library.objects.get_or_create(
        name=f"lib{int(allow)}",
        defaults={"mount_path": str(tmp_path / f"lib{int(allow)}"), "allow_delete": allow},
    )
    root = tmp_path / lib.name
    (root / "M 31").mkdir(parents=True, exist_ok=True)
    (root / "M 31" / name).write_bytes(b"x" * 10)
    f = Frame.objects.create(
        sha256=name.ljust(64, "0")[:64],
        size_bytes=10,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        exptime_s=60,
    )
    Copy.objects.create(
        frame=f,
        library=lib,
        rel_path=f"M 31/{name}",
        st_dev=1,
        st_ino=1,
        st_size=10,
        st_mtime_ns=1,
        first_seen_at=T,
        last_seen_at=T,
    )
    return f, lib


def test_binning_moves_to_quarantine_and_restore_brings_it_back(tmp_path):
    f, lib = sub(tmp_path, "a.fits")
    assert bin_frames([f.pk], "Marked for deletion", by="owner") == {"binned": 1, "moved": 1, "hidden": 0}
    f.refresh_from_db()
    c = Copy.objects.get(frame=f)
    assert (
        f.status == FrameStatus.BINNED and f.purge_after is not None and f.bin_reason == "Marked for deletion"
    )
    assert c.rel_path == f"{QUARANTINE}/M 31/a.fits" and (tmp_path / lib.name / c.rel_path).exists()
    assert not (tmp_path / lib.name / "M 31/a.fits").exists()
    assert restore_frames([f.pk])["restored"] == 1
    f.refresh_from_db()
    assert f.status == FrameStatus.CATALOGUED and (tmp_path / lib.name / "M 31/a.fits").exists()
    assert Copy.objects.get(frame=f).rel_path == "M 31/a.fits"


def test_a_library_not_allowed_only_hides_and_never_deletes(tmp_path):
    f, lib = sub(tmp_path, "b.fits", allow=False)
    assert bin_frames([f.pk], "Marked for deletion")["hidden"] == 1
    f.refresh_from_db()
    assert f.status == FrameStatus.BINNED and f.purge_after is None
    assert (tmp_path / lib.name / "M 31/b.fits").exists()
    assert purge_due(timezone.now() + timedelta(days=365))["deleted"] == 0
    assert (tmp_path / lib.name / "M 31/b.fits").exists()


def test_purge_deletes_the_file_but_keeps_the_record(tmp_path):
    f, lib = sub(tmp_path, "c.fits")
    bin_frames([f.pk], "Marked for deletion")
    assert purge_due(timezone.now() + timedelta(days=29))["deleted"] == 0  # not yet
    assert purge_due(timezone.now() + timedelta(days=31))["deleted"] == 1
    f.refresh_from_db()
    assert f.status == FrameStatus.DELETED and f.exptime_s == 60
    assert not (tmp_path / lib.name / QUARANTINE / "M 31/c.fits").exists()


def test_long_rejected_subs_bin_themselves_unless_recent(tmp_path):
    old, _ = sub(tmp_path, "d.fits")
    new, _ = sub(tmp_path, "e.fits")
    for f, age in ((old, 40), (new, 10)):
        MachineGrade.objects.create(frame=f, verdict="reject", reason="cloud")
        MachineGrade.objects.filter(frame=f).update(graded_at=timezone.now() - timedelta(days=age))
    assert auto_bin() == {"binned": 1}
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.status == FrameStatus.BINNED and old.bin_reason == "Rejected for over 30 days: cloud"
    assert new.status == FrameStatus.CATALOGUED


def test_the_bin_api_bins_lists_and_restores(tmp_path, admin_client):
    f, _ = sub(tmp_path, "f.fits")
    r = admin_client.post("/api/v1/bin", {"sha256s": [f.pk]}, content_type="application/json")
    assert r.status_code == 200 and r.json()["moved"] == 1
    listed = admin_client.get("/api/v1/bin").json()
    assert (
        listed["total"] == 1
        and listed["rows"][0]["name"] == "f.fits"
        and listed["rows"][0]["reason"] == "Binned by hand"
    )
    assert listed["bytes_in_quarantine"] == 10 and listed["purge_after_days"] == 30
    r = admin_client.post("/api/v1/bin/restore", {"sha256s": [f.pk]}, content_type="application/json")
    assert r.json()["restored"] == 1 and admin_client.get("/api/v1/bin").json()["total"] == 0


def test_history_still_counts_binned_subs(tmp_path, admin_client):
    from apps.catalogue.models import Dataset

    d = Dataset.objects.create(group_key="m31", target="M 31", filter_norm="L", display_name="M 31 · L")
    f, _ = sub(tmp_path, "g.fits")
    Frame.objects.filter(pk=f.pk).update(dataset=d)
    before = admin_client.get("/api/v1/library/stats").json()
    bin_frames([f.pk], "Binned by hand")
    after = admin_client.get("/api/v1/library/stats").json()
    assert (
        before["frames"] == after["frames"] == 1
        and after["binned"] == 1
        and after["by_filter"] == {"L": 0.02}
    )
