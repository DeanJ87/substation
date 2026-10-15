"""Spec 014: a backup holds every table and restores exactly, in one transaction; another version's backup is refused
with the reason."""

import json
import tarfile
from datetime import date

import pytest

from apps.catalogue.models import Night
from substation.backup import BackupError, list_backups, make_backup, prune, read_manifest, restore

pytestmark = pytest.mark.django_db(transaction=True)


def test_backup_and_restore_round_trip(tmp_path):
    Night.objects.create(site_key="home", date=date(2026, 10, 14))
    path = make_backup(tmp_path)
    m = read_manifest(path)
    assert m["tables"]["catalogue_night"] == 1 and "substation_tasks_task" not in m["tables"]
    Night.objects.all().delete()
    Night.objects.create(site_key="away", date=date(2026, 1, 1))
    out = restore(path)
    assert list(Night.objects.values_list("site_key", flat=True)) == ["home"] and out["tables"] > 10
    n = Night.objects.create(site_key="next", date=date(2026, 10, 15))  # ids carry on after the restored ones
    assert n.pk > Night.objects.get(site_key="home").pk


def test_a_backup_from_another_version_is_refused(tmp_path):
    path = make_backup(tmp_path)
    with tarfile.open(path, "r:gz") as tar:
        members = {mm.name: tar.extractfile(mm).read() for mm in tar.getmembers() if mm.isfile()}
    manifest = json.loads(members["manifest.json"])
    manifest["schema"] = manifest["schema"][:-1]
    members["manifest.json"] = json.dumps(manifest).encode()
    other = tmp_path / "substation-backup-other.tar.gz"
    import io

    with tarfile.open(other, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(BackupError, match="different version"):
        restore(other)


def test_only_the_newest_are_kept(tmp_path):
    for i in range(3):
        (tmp_path / f"substation-backup-2026-10-1{i}_030000.tar.gz").write_bytes(b"x")
    assert prune(2, tmp_path) == 1 and len(list_backups(tmp_path)) == 2


@pytest.mark.django_db
def test_backup_settings_are_checked(admin_client):
    bad = admin_client.patch(
        "/api/v1/settings", {"processing": {"backup": {"time": "25:00"}}}, content_type="application/json"
    )
    assert bad.status_code == 422 and "HH:MM" in bad.json()["message"]
    ok = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"backup": {"time": "04:15", "keep": 7, "folder": "/backups"}}},
        content_type="application/json",
    )
    assert ok.json()["processing"]["backup"]["keep"] == 7
    assert admin_client.get("/api/v1/backups").json()["folder"] == "/backups"
