"""Atomic claim of the next task (research R2): one IMMEDIATE transaction, UPDATE … RETURNING (SQLite ≥ 3.35).

Ordering: priority (high first), then enqueue time. Tasks in the `siril_heavy` slot only start while fewer
than the configured number of heavy tasks are running (spec 005). While the queue is paused ("Pause new work"),
only ingest tasks start, so new subs are still catalogued.
"""

from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from .models import Task

_CLAIM_SQL = """
UPDATE substation_tasks_task
   SET status = 'running', worker_id = %s, started_at = %s, heartbeat_at = %s,
       attempts = attempts + 1, progress = NULL, progress_note = ''
 WHERE id = (
       SELECT id FROM substation_tasks_task
        WHERE status = 'ready' AND run_after <= %s
          AND (queue = 'ingest'
               OR NOT COALESCE((SELECT queue_paused FROM libraries_installationsettings LIMIT 1), 0))
          {queues}
          AND (slot = 'light'
               OR (SELECT COUNT(*) FROM substation_tasks_task
                    WHERE status = 'running' AND slot = 'siril_heavy') < %s)
        ORDER BY priority DESC, enqueued_at ASC
        LIMIT 1)
RETURNING id
"""


def queue_filter() -> tuple[list[str], list[str]]:
    """Which queues this container's workers take (spec 010): SUBSTATION_ONLY_QUEUES (the finisher: "finish") or
    SUBSTATION_SKIP_QUEUES (the main workers, when a finisher runs: "finish"). Neither set: every queue."""
    import os

    split = lambda v: [q.strip() for q in (v or "").split(",") if q.strip()]  # noqa: E731
    return split(os.environ.get("SUBSTATION_ONLY_QUEUES")), split(os.environ.get("SUBSTATION_SKIP_QUEUES"))


def claim(
    worker_id: str, heavy_slots: int = 1, only: list[str] | None = None, skip: list[str] | None = None
) -> Task | None:
    now = timezone.now()
    db_now = connection.ops.adapt_datetimefield_value(now)
    if only is None and skip is None:
        only, skip = queue_filter()
    clause, params = "", []
    if only:
        clause = f"AND queue IN ({', '.join(['%s'] * len(only))})"
        params = list(only)
    elif skip:
        clause = f"AND queue NOT IN ({', '.join(['%s'] * len(skip))})"
        params = list(skip)
    sql = _CLAIM_SQL.replace("{queues}", clause)
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(sql, [worker_id, db_now, db_now, db_now, *params, heavy_slots])
        row = cur.fetchone()
    if row is None:
        return None
    return Task.objects.get(pk=row[0])
