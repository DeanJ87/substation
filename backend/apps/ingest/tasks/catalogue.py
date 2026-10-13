"""ingest.catalogue (T052): read the header, record metadata with sources, classify, assign night and
dataset, and tell the browser."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Copy, Frame, FrameStatus, HeaderSnapshot
from apps.catalogue.services.grouping import refresh_dataset
from apps.libraries.models import Library
from substation.events.emit import emit
from substation.tasks import station_task

from ..completeness import expected_size
from ..fields import extract
from ..headers import read_header
from ..resolve import record_header_values, resolve_frame


def _readable_copy(frame: Frame, library_id: int, rel_path: str) -> Path | None:
    candidates = [(library_id, rel_path)] + list(
        frame.copies.filter(present=True).values_list("library_id", "rel_path")
    )
    for lib_id, rel in candidates:
        lib = Library.objects.filter(pk=lib_id).first()
        if lib is not None and (Path(lib.mount_path) / rel).is_file():
            return Path(lib.mount_path) / rel
    return None


@station_task(queue_name="ingest", max_attempts=3)
def catalogue_frame(sha256: str, library_id: int, rel_path: str) -> dict:
    frame = Frame.objects.get(pk=sha256)
    if frame.status == FrameStatus.IGNORED:
        return {"result": "ignored"}
    path = _readable_copy(frame, library_id, rel_path)
    if path is None:
        return {"result": "no readable copy"}
    res = read_header(path)
    need = expected_size(path) if settings.INGEST_VERIFY_COMPLETE else None
    if res.ok and need is not None and frame.size_bytes < need:
        res.error = f"File truncated: {frame.size_bytes:,} of {need:,} bytes."
    with transaction.atomic():
        frame = Frame.objects.select_for_update().get(pk=sha256)
        frame.format = res.format
        if not res.ok:
            frame.status, frame.error = FrameStatus.ERROR, res.error
            frame.catalogued_at = timezone.now()
            frame.save()
        else:
            frame.error = None
            frame.status = FrameStatus.CATALOGUED
            frame.image_count = len(res.images)
            frame.integration_index = res.integration_index()
            frame.headers.all().delete()
            HeaderSnapshot.objects.bulk_create(
                [
                    HeaderSnapshot(
                        frame=frame,
                        image_index=i.index,
                        image_id=i.image_id,
                        geometry=":".join(map(str, i.geometry)),
                        sample_format=i.sample_format,
                        keywords=_json_safe(i.keywords_json()),
                        properties=_json_safe(i.properties),
                    )
                    for i in res.images
                ]
            )
            record_header_values(frame, extract(res.primary()))
            frame.catalogued_at = timezone.now()
            old, new = resolve_frame(frame, has_integration=res.integration_index() is not None)
    if res.ok:
        from apps.ingest.processed import set_aside

        if set_aside(frame):  # 8-bit, or a PixInsight copy of a raw sub we already have: not a sub
            from apps.ingest.tasks.ignore import apply_ignore

            apply_ignore.call([frame.sha256], "content", None, False)
            frame.refresh_from_db()
    if res.ok:  # after the commit: recounting a big dataset mustn't hold the write lock
        refresh_dataset(old)
        if new is not None and new != old:
            refresh_dataset(new)
    emit(
        "frame.catalogued",
        {
            "sha256": sha256,
            "frame_type": frame.frame_type,
            "dataset_id": frame.dataset_id,
            "night": frame.night.date.isoformat() if frame.night else None,
            "path": rel_path,
            "status": frame.status,
        },
    )
    d = frame.dataset
    if d is not None:
        emit(
            "dataset.updated",
            {
                "dataset_id": d.pk,
                "sub_count": d.sub_count,
                "integration_s": d.integration_s,
                "state": d.state,
            },
        )
    return {"result": frame.status, "frame_type": frame.frame_type}


def _json_safe(d: dict) -> dict:
    import json

    return json.loads(json.dumps(d, default=str))


__all__ = ["catalogue_frame", "Copy"]
