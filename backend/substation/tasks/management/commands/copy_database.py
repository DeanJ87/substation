"""`manage.py copy_database <sqlite file>`: move an installation from SQLite to PostgreSQL (005-DR-24).

Run it against the new, migrated PostgreSQL database (SUBSTATION_DATABASE_URL set) with SubStation stopped, so
nothing writes to the SQLite file while it is read. Every row of every table is copied with its own id, in one
transaction: a failure leaves PostgreSQL as it was. The target must hold nothing but what `migrate` creates;
`--replace` empties it first. Sequences are reset afterwards so new rows don't collide with copied ids.
"""

from __future__ import annotations

import time
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, connections, transaction

SOURCE = "copy_source"
BATCH = 2000


class Command(BaseCommand):
    help = "Copy every row from a SubStation SQLite database into the configured PostgreSQL database."

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument("sqlite", help="path to the SQLite database file (substation.db)")
        parser.add_argument("--replace", action="store_true", help="empty the PostgreSQL tables first")

    def handle(self, *args, **opts) -> None:
        src = Path(opts["sqlite"])
        if not src.is_file():
            raise CommandError(f"No SQLite database at {src}.")
        if connection.vendor != "postgresql":
            raise CommandError("Set SUBSTATION_DATABASE_URL to the PostgreSQL database to copy into.")
        connections.databases[SOURCE] = {
            **connections.databases["default"],
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": f"file:{src}?mode=ro",
            "OPTIONS": {"uri": True},
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
        }
        self._check_migrations()
        models = [
            m
            for m in apps.get_models(include_auto_created=True)
            if m._meta.managed and not m._meta.proxy and m._meta.db_table in self._source_tables()
        ]
        tables = [m._meta.db_table for m in models]
        started = time.monotonic()
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")  # SQLite holds UTC times without a zone
                cur.execute("SET CONSTRAINTS ALL DEFERRED")  # rows arrive in any order; checked at commit
                busy = [t for t in tables if t != "django_migrations" and self._count(cur, t)]
                # migrate seeds a few tables itself (content types, permissions, groups); real data means a user or
                # a catalogued frame, and that is only replaced when asked
                real = [t for t in ("auth_user", "catalogue_frame") if t in busy]
                if real and not opts["replace"]:
                    raise CommandError(
                        f"PostgreSQL already has data ({', '.join(real)}). Pass --replace to empty it first."
                    )
                if busy:
                    cur.execute(
                        "TRUNCATE " + ", ".join(connection.ops.quote_name(t) for t in busy) + " CASCADE"
                    )
            total = 0
            for model in models:
                if model._meta.db_table == "django_migrations":
                    continue
                n = self._copy(model)
                total += n
                if n:
                    self.stdout.write(f"{model._meta.db_table}: {n:,}")
            with connection.cursor() as cur:
                for sql in connection.ops.sequence_reset_sql(no_style(), models):
                    cur.execute(sql)
        self.stdout.write(
            self.style.SUCCESS(f"Copied {total:,} rows from {src} in {time.monotonic() - started:.0f} s.")
        )

    def _source_tables(self) -> set[str]:
        with connections[SOURCE].cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            return {r[0] for r in cur.fetchall()}

    def _check_migrations(self) -> None:
        """Both databases must be at the same migrations, or columns won't line up."""

        def applied(alias: str) -> set[tuple[str, str]]:
            with connections[alias].cursor() as cur:
                cur.execute("SELECT app, name FROM django_migrations")
                return {(a, n) for a, n in cur.fetchall()}

        missing = applied(SOURCE) - applied("default")
        if missing:
            raise CommandError(
                f"PostgreSQL is missing {len(missing)} migrations the SQLite database has "
                f"(e.g. {sorted(missing)[0]}). Run migrate with this version first."
            )
        extra = applied("default") - applied(SOURCE)
        if extra:
            raise CommandError(
                f"PostgreSQL has {len(extra)} migrations the SQLite database hasn't (e.g. {sorted(extra)[0]}). "
                "Copy with the version the SQLite database was last run with, then upgrade."
            )

    @staticmethod
    def _count(cur, table: str) -> int:  # noqa: ANN001
        cur.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)}")
        return int(cur.fetchone()[0])

    def _copy(self, model) -> int:  # noqa: ANN001
        """Table to table, column by column, values as stored: no model code runs, so nothing is changed on the
        way (auto_now stamps, defaults). SQLite keeps booleans as 0/1; those become true/false."""
        q = connection.ops.quote_name
        table = model._meta.db_table
        with connections[SOURCE].cursor() as cur:
            cur.execute(f"PRAGMA table_info({q(table)})")
            src_cols = [r[1] for r in cur.fetchall()]
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s", [table]
            )
            dst = dict(cur.fetchall())
        cols = [c for c in src_cols if c in dst]
        booleans = {i for i, c in enumerate(cols) if dst[c] == "boolean"}
        insert = f"INSERT INTO {q(table)} ({', '.join(q(c) for c in cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        n = 0
        with connections[SOURCE].cursor() as read, connection.cursor() as write:
            read.execute(f"SELECT {', '.join(q(c) for c in cols)} FROM {q(table)}")
            while rows := read.fetchmany(BATCH):
                if booleans:
                    rows = [
                        [bool(v) if i in booleans and v is not None else v for i, v in enumerate(r)]
                        for r in rows
                    ]
                write.executemany(insert, rows)
                n += len(rows)
        return n
