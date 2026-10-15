"""Database backups (spec 014): every table written with PostgreSQL's COPY into one .tar.gz with a manifest, kept in a
folder you choose, and restored from there in one transaction. No pg_dump is needed, so the client never has to match
the server's version. Your files are not in it: only what SubStation knows about them."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

log = logging.getLogger("substation.backup")

# work in flight, live events and sign-ins: meaningless in another moment, so neither saved nor replaced
TRANSIENT = {
    "substation_tasks_task",
    "substation_tasks_worker",
    "substation_tasks_resourcesample",
    "substation_tasks_lease",
    "substation_events_event",
    "django_session",
    "django_migrations",
}
PREFIX = "substation-backup-"


class BackupError(Exception):
    """Said plainly, for the page."""


def folder() -> Path:
    from apps.processing.config import processing_settings

    return Path((processing_settings().get("backup") or {}).get("folder") or settings.BACKUP_DIR)


def _tables() -> list[str]:
    with connection.cursor() as cur:
        return sorted(t for t in connection.introspection.table_names(cur) if t not in TRANSIENT)


def _schema() -> list[list[str]]:
    with connection.cursor() as cur:
        cur.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
        return [list(r) for r in cur.fetchall()]


def make_backup(dest: Path | None = None) -> Path:
    """Write a backup and return its path. Written under a temporary name and renamed when complete, so a half-written
    backup is never listed."""
    dest = dest or folder()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(
            f"Can't write to {dest} ({exc.strerror or exc}). Check the folder is mounted and writable."
        ) from None
    stamp = timezone.localtime().strftime("%Y-%m-%d_%H%M%S")
    final = dest / f"{PREFIX}{stamp}.tar.gz"
    part = final.with_suffix(".gz.part")
    counts: dict[str, int] = {}
    tables = _tables()
    started = time.monotonic()
    outermost = not connection.in_atomic_block
    with tempfile.TemporaryDirectory(dir=dest) as tmp, transaction.atomic():
        if outermost:  # one consistent moment for every table (inside another transaction it already is one)
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        raw = connection.connection  # psycopg's own, for COPY
        with tarfile.open(part, "w:gz") as tar:
            for t in tables:
                path = Path(tmp) / f"{t}.csv"
                with raw.cursor() as rc, path.open("wb") as fh:
                    with rc.copy(f'COPY "{t}" TO STDOUT (FORMAT csv, HEADER)') as copy:
                        for chunk in copy:
                            fh.write(chunk)
                    rc.execute(f'SELECT COUNT(*) FROM "{t}"')
                    counts[t] = rc.fetchone()[0]
                tar.add(path, arcname=f"tables/{t}.csv")
                path.unlink()
            manifest = {
                "format": 1,
                "made_at": timezone.now().isoformat(),
                "substation": settings.SUBSTATION_VERSION or "dev",
                "schema": _schema(),
                "tables": counts,
            }
            data = json.dumps(manifest, indent=1).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(data)
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    part.replace(final)
    log.info("Backup %s: %s tables in %.0f s", final.name, len(tables), time.monotonic() - started)
    return final


def read_manifest(path: Path) -> dict:
    with tarfile.open(path, "r:gz") as tar:
        f = tar.extractfile("manifest.json")
        if f is None:
            raise BackupError(f"{path.name} has no manifest: not a SubStation backup.")
        return json.loads(f.read())


def list_backups(dest: Path | None = None) -> list[dict]:
    dest = dest or folder()
    out = []
    for p in sorted(dest.glob(f"{PREFIX}*.tar.gz"), reverse=True) if dest.is_dir() else []:
        st = p.stat()
        out.append(
            {
                "name": p.name,
                "size_bytes": st.st_size,
                "made_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone()),
            }
        )
    return out


def prune(keep: int, dest: Path | None = None) -> int:
    """Keep the newest `keep` backups; delete the rest. Returns how many went."""
    gone = 0
    for b in list_backups(dest)[max(keep, 1) :]:
        with contextlib.suppress(OSError):
            ((dest or folder()) / b["name"]).unlink()
            gone += 1
    return gone


def restore(path: Path) -> dict:
    """Replace every saved table with the backup's rows, in one transaction: it all applies or nothing does. Only a
    backup of this schema is accepted; an older or newer one says so."""
    manifest = read_manifest(path)
    have = _schema()
    if manifest.get("schema") != have:
        theirs = {tuple(x) for x in manifest.get("schema", [])}
        ours = {tuple(x) for x in have}
        newer = sorted(f"{a}.{n}" for a, n in ours - theirs)[:3]
        older = sorted(f"{a}.{n}" for a, n in theirs - ours)[:3]
        why = (
            f"this SubStation has changes the backup doesn't ({', '.join(newer)})"
            if newer
            else f"the backup is from a newer SubStation ({', '.join(older)})"
        )
        raise BackupError(
            f"{path.name} was made by a different version of SubStation: {why}. Restore it with "
            f"the version that made it ({manifest.get('substation', 'unknown')})."
        )
    tables = [t for t in _tables() if t in manifest["tables"]]
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(path, "r:gz") as tar:
            for t in tables:
                member = tar.getmember(f"tables/{t}.csv")
                tar.extract(member, tmp, filter="data")
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
            raw = connection.connection
            for t in tables:
                src = Path(tmp) / "tables" / f"{t}.csv"
                with src.open("rb") as fh:
                    header = fh.readline().decode().strip()
                    cols = ", ".join(f'"{c}"' for c in header.split(","))
                    fh.seek(0)
                    with (
                        raw.cursor() as rc,
                        rc.copy(f'COPY "{t}" ({cols}) FROM STDIN (FORMAT csv, HEADER)') as copy,
                    ):
                        while chunk := fh.read(1 << 20):
                            copy.write(chunk)
            _reset_sequences(cur, tables)
    return {"tables": len(tables), "rows": sum(manifest["tables"].get(t, 0) for t in tables)}


def _reset_sequences(cur, tables: list[str]) -> None:  # noqa: ANN001
    """Every serial column carries on after the highest restored id."""
    cur.execute(
        """
        SELECT c.relname, a.attname, pg_get_serial_sequence(quote_ident(c.relname), a.attname)
        FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r' AND c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped
          AND pg_get_serial_sequence(quote_ident(c.relname), a.attname) IS NOT NULL
        """,
        [tables],
    )
    for table, col, seq in cur.fetchall():
        cur.execute(f'SELECT setval(%s, COALESCE((SELECT MAX("{col}") FROM "{table}"), 0) + 1, false)', [seq])


def backup_due(now: datetime | None = None) -> bool:
    """Once a day at the set time, if switched on and none has been made since then."""
    from apps.processing.config import processing_settings

    cfg = processing_settings().get("backup") or {}
    if not cfg.get("enabled", True):
        return False
    now = timezone.localtime(now)
    hh, mm = (int(x) for x in str(cfg.get("time", "03:30")).split(":"))
    slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < slot:
        return False
    from substation.tasks.models import Task

    # one try a day: a folder that can't be written fails once, on Activity, not every five minutes
    if Task.objects.filter(name__endswith=".backup_database", enqueued_at__gte=slot).exists():
        return False
    latest = list_backups()
    return not latest or latest[0]["made_at"] < slot
