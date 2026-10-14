"""ingest.hash (T051): wait for a stable file, hash it, record the frame and this copy.

Stability: a file modified in the last 2 s is rescheduled ("still being written") without counting a
failed attempt; after 5 minutes of continuous change it is recorded as an error. The file is stat'ed again
after hashing, and rescheduled if it changed meanwhile, so a partial file never becomes a frame.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Copy, CopyEvent, CopyEventKind, Frame, FrameStatus
from apps.catalogue.services.ignore import PathRules, content_ignored
from apps.catalogue.services.tracking import mark_present, touch_dataset
from apps.catalogue.services.verdicts import apply_bad_prefix
from apps.libraries.models import Library
from substation.tasks import Reschedule, enqueue, report_progress, station_task

from ..completeness import expected_size
from ..headers import file_format
from ..pathcheck import Fingerprint, priority_for

QUIET_S = 2.0
GIVE_UP_S = 300.0
CHUNK = 8 << 20


def sha256_file(path: Path, size: int) -> str:
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            done += len(chunk)
            if size > 64 << 20:
                report_progress(done / size, f"hashing {path.name}")
    return h.hexdigest()


@station_task(queue_name="ingest", max_attempts=5)
def hash_file(library_id: int, rel_path: str, first_seen: float) -> dict:
    lib = Library.objects.get(pk=library_id)
    path = Path(lib.mount_path) / rel_path
    # the rules again, now: a rule added after this file was queued (darks shot in daylight, ignored while
    # Robocopy was still copying them, 2026-10-14) must still keep it out
    if PathRules.load().matches(library_id, rel_path):
        return {"result": "ignored by a rule"}
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return {"result": "gone"}  # moved or deleted before we got to it; the next sweep sees where it went
    if time.time() - st.st_mtime < QUIET_S:
        if time.time() - first_seen > GIVE_UP_S:
            raise RuntimeError(
                f"{rel_path} kept changing for 5 minutes; it will be retried on the next sweep."
            )
        raise Reschedule(QUIET_S, f"{path.name} is still being written")
    need = expected_size(path) if settings.INGEST_VERIFY_COMPLETE else None
    # A short file modified recently is still arriving; an old one is truncated, and is catalogued with
    # that error (catalogue_frame checks again) rather than waited on.
    recent = time.time() - st.st_mtime < GIVE_UP_S and time.time() - first_seen < GIVE_UP_S
    if need is not None and st.st_size < need and recent:
        raise Reschedule(QUIET_S, f"{path.name} is still being written ({st.st_size} of {need} bytes)")
    digest = sha256_file(path, st.st_size)
    st_after = os.stat(path)
    if Fingerprint.of(st_after) != Fingerprint.of(st):
        raise Reschedule(QUIET_S, f"{path.name} changed while it was being read")

    now = timezone.now()
    name = os.path.basename(rel_path)
    orphan: Frame | None = None
    with transaction.atomic():
        frame, created = Frame.objects.get_or_create(
            sha256=digest,
            defaults={"size_bytes": st.st_size, "format": file_format(path), "first_seen_at": now},
        )
        copy = Copy.objects.filter(library=lib, rel_path=rel_path).first()
        fp = {"st_dev": st.st_dev, "st_ino": st.st_ino, "st_size": st.st_size, "st_mtime_ns": st.st_mtime_ns}
        if copy is None:
            # Known content at a new path: a copy, or a move if a copy of it has gone missing (T063). A move
            # takes over the missing copy's place, so the frame doesn't list a path that no longer exists.
            details: dict = {"path": rel_path}
            kind = CopyEventKind.DISCOVERED if created else CopyEventKind.COPIED
            gone = (
                None
                if created
                else Copy.objects.filter(frame=frame, present=False).order_by("-missing_since").first()
            )
            if gone is not None:
                kind, details = (
                    CopyEventKind.MOVED,
                    {"from": f"{gone.library.name}/{gone.rel_path}", "to": rel_path},
                )
                gone.delete()
            copy = Copy.objects.create(
                frame=frame,
                library=lib,
                rel_path=rel_path,
                is_bad_prefixed=name.startswith("BAD_"),
                first_seen_at=now,
                last_seen_at=now,
                **fp,
            )
            CopyEvent.objects.create(kind=kind, frame=frame, copy=copy, library=lib, details=details)
        else:
            for k, v in fp.items():
                setattr(copy, k, v)
            if copy.frame_id != frame.pk:  # same path, new content: the old frame loses this copy
                old = copy.frame
                CopyEvent.objects.create(
                    kind=CopyEventKind.REPLACED,
                    frame=old,
                    copy=copy,
                    library=lib,
                    details={"path": rel_path, "new_sha256": digest},
                )
                if not Copy.objects.filter(frame=old).exclude(pk=copy.pk).exists():
                    old.status = FrameStatus.MISSING
                    old.save(update_fields=["status"])
                    orphan = old
            elif not copy.present:
                CopyEvent.objects.create(
                    kind=CopyEventKind.REAPPEARED,
                    frame=frame,
                    copy=copy,
                    library=lib,
                    details={"path": rel_path},
                )
            copy.frame = frame
            copy.is_bad_prefixed = name.startswith("BAD_")
            copy.present, copy.last_seen_at, copy.missing_since = True, now, None
            copy.save()
    if orphan is not None:
        touch_dataset(orphan.dataset)
    verdict_changed = apply_bad_prefix(frame)
    if not created:
        mark_present(frame)
        if verdict_changed:
            touch_dataset(frame.dataset)
    if created and content_ignored(digest):
        Frame.objects.filter(pk=digest).update(status=FrameStatus.IGNORED)
        return {"result": "ignored", "sha256": digest}
    if created:
        from .catalogue import catalogue_frame

        # One above its hash's priority, so a sub is catalogued straight after hashing rather than after
        # the whole backlog has been hashed.
        enqueue(
            catalogue_frame,
            digest,
            lib.pk,
            rel_path,
            dedupe_key=f"catalogue:{digest}",
            priority=priority_for(st) + 1,
        )
    return {"result": "new" if created else "known", "sha256": digest}
