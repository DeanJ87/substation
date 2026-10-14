"""005-DR-24: `copy_database` moves an installation from SQLite to PostgreSQL, rows and ids as they were."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from django.db import connection

from tests.conftest import BACKEND, manage

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not os.environ.get("SUBSTATION_DATABASE_URL"),
        reason="copies into PostgreSQL; runs in the PostgreSQL job",
    ),
]


def _sqlite(tmp_path):
    """A migrated SQLite installation with a collection, a dataset and a frame in it."""
    db = tmp_path / "old.db"
    env = {**os.environ, "SUBSTATION_DB_PATH": str(db), "DJANGO_SETTINGS_MODULE": "substation.settings"}
    env.pop("SUBSTATION_DATABASE_URL")
    run = lambda *a: subprocess.run([sys.executable, str(BACKEND / "manage.py"), *a], env=env, check=True)  # noqa: E731
    run("migrate", "--noinput", "-v", "0")
    code = (
        "from datetime import datetime, UTC\n"
        "from apps.catalogue.models import Collection, Dataset, Frame\n"
        "c = Collection.objects.create(name='M 31 - Andromeda Galaxy')\n"
        "d = Dataset.objects.create(group_key='k', display_name='M 31 · L', target='M 31', filter_norm='L',"
        " collection=c, sub_count=1)\n"
        "Frame.objects.create(sha256='a'*64, size_bytes=1, format='fits', status='catalogued',"
        " first_seen_at=datetime(2026, 9, 1, 21, 0, tzinfo=UTC), dataset=d, xbin=1)\n"
    )
    subprocess.run([sys.executable, str(BACKEND / "manage.py"), "shell", "-c", code], env=env, check=True)
    return db


def test_rows_and_ids_arrive_as_they_were(tmp_path):
    from apps.catalogue.models import Collection, Dataset, Frame

    db = _sqlite(tmp_path)
    # in its own process, as an operator would run it, against this test's PostgreSQL database
    p = manage(
        "copy_database", str(db), "--replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    out, _ = p.communicate(timeout=120)
    assert p.returncode == 0, out
    c = Collection.objects.get()
    d = Dataset.objects.get()
    f = Frame.objects.get()
    assert c.name == "M 31 - Andromeda Galaxy" and d.collection_id == c.pk and f.dataset_id == d.pk
    assert f.first_seen_at.isoformat() == "2026-09-01T21:00:00+00:00"
    assert Collection.objects.create(name="new").pk > c.pk  # sequences follow the copied ids
    assert connection.vendor == "postgresql"
