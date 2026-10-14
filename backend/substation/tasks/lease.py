"""Leases: one holder at a time across processes and containers (an atomic upsert)."""

from __future__ import annotations

from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

_SQL = """
INSERT INTO substation_tasks_lease (name, holder, expires_at) VALUES (%s, %s, %s)
ON CONFLICT(name) DO UPDATE SET holder = excluded.holder, expires_at = excluded.expires_at
 WHERE substation_tasks_lease.holder = excluded.holder OR substation_tasks_lease.expires_at < %s
"""


def acquire(name: str, holder: str, ttl_s: float = 15) -> bool:
    """Take or renew `name` for `holder`. True if `holder` holds it afterwards."""
    now = timezone.now()
    ops = connection.ops
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            _SQL,
            [
                name,
                holder,
                ops.adapt_datetimefield_value(now + timedelta(seconds=ttl_s)),
                ops.adapt_datetimefield_value(now),
            ],
        )
        cur.execute("SELECT holder FROM substation_tasks_lease WHERE name = %s", [name])
        row = cur.fetchone()
    return row is not None and row[0] == holder


def release(name: str, holder: str) -> None:
    from .models import Lease

    Lease.objects.filter(name=name, holder=holder).delete()
