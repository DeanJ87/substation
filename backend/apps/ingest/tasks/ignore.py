"""ingest.apply_ignore (T090): after an ignore rule is added or undone, bring the frames it covers in line
(ignored, or restored and processed), and for an undone path rule sweep again so files never hashed are
queued."""

from __future__ import annotations

from django.utils import timezone

from apps.catalogue.models import Frame, IgnoreKind
from apps.catalogue.services.ignore import refresh_frames
from apps.libraries.models import Library
from substation.tasks import PRIORITY_LIVE, station_task


@station_task(queue_name="ingest", priority=PRIORITY_LIVE, max_attempts=3)
def apply_ignore(shas: list[str], kind: str, library_id: int | None, undone: bool) -> dict:
    changed = refresh_frames(list(Frame.objects.filter(pk__in=shas)))
    if undone and kind != IgnoreKind.CONTENT:
        libs = Library.objects.filter(enabled=True)
        if library_id is not None:
            libs = libs.filter(pk=library_id)
        libs.update(rescan_requested_at=timezone.now())
    return {"frames_changed": changed}
