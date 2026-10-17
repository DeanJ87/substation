"""ingest.move_collection (spec 013): archive a collection's files, or bring them back, on the bulk queue. The work
and its checkpoints live in apps.catalogue.services.archive; a restart picks up from the files already moved."""

from __future__ import annotations

from substation.tasks import PRIORITY_BULK, station_task


@station_task(queue_name="ingest", priority=PRIORITY_BULK, max_attempts=3)
def move_collection(move_id: int) -> dict:
    from apps.catalogue.services.archive import run_move

    return run_move(move_id)
