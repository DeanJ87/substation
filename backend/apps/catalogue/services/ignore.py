"""Ignore rules in effect (T090). Path rules (folder, glob) stop files being hashed or catalogued; content
rules stop a frame being catalogued wherever it appears. A frame whose present copies are all covered is
`ignored` and leaves its dataset; undoing a rule restores it and queues anything never processed."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass

from django.db import transaction

from substation.events.emit import emit

from ..models import Copy, Dataset, Frame, FrameStatus, IgnoreKind, IgnoreRule
from .tracking import touch_dataset


@dataclass(frozen=True)
class PathRules:
    """Active folder and glob rules, loaded once per sweep or batch of events."""

    rules: tuple[tuple[int | None, str, str], ...]  # (library id, kind, value)

    @classmethod
    def load(cls) -> PathRules:
        return cls(
            tuple(
                IgnoreRule.objects.filter(
                    active=True, kind__in=[IgnoreKind.FOLDER, IgnoreKind.GLOB]
                ).values_list("library_id", "kind", "value")
            )
        )

    def matches(self, library_id: int, rel_path: str) -> bool:
        return any(
            path_rule_matches(kind, value, rel_path)
            for lib, kind, value in self.rules
            if lib is None or lib == library_id
        )


def path_rule_matches(kind: str, value: str, rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/")
    if kind == IgnoreKind.FOLDER:
        folder = value.strip("/")
        return folder == "" or rel.startswith(folder + "/")
    if kind == IgnoreKind.GLOB:
        return fnmatch.fnmatchcase(rel, value) or fnmatch.fnmatchcase(os.path.basename(rel), value)
    return False


def content_ignored(sha256: str) -> bool:
    return IgnoreRule.objects.filter(active=True, kind=IgnoreKind.CONTENT, value=sha256).exists()


def _covered(frame: Frame, path_rules: PathRules) -> bool:
    if content_ignored(frame.sha256):
        return True
    copies = list(Copy.objects.filter(frame=frame, present=True).values_list("library_id", "rel_path"))
    return bool(copies) and all(path_rules.matches(lib, rel) for lib, rel in copies)


def refresh_frames(frames: list[Frame]) -> int:
    """Bring each frame's ignored status in line with the active rules. Returns frames changed."""
    from apps.ingest.tasks.catalogue import catalogue_frame
    from substation.tasks import PRIORITY_BULK, enqueue

    rules = PathRules.load()
    touched: dict[int, Dataset] = {}
    changed = 0
    for frame in frames:
        if frame.status in (FrameStatus.BINNED, FrameStatus.DELETED):  # the bin decides these (spec 011)
            continue
        covered = _covered(frame, rules)
        if covered == (frame.status == FrameStatus.IGNORED):
            continue
        with transaction.atomic():
            old_ds = frame.dataset
            if covered:
                frame.status, frame.dataset = FrameStatus.IGNORED, None
                frame.save(update_fields=["status", "dataset"])
            elif frame.catalogued_at is None:  # never processed: do it now
                frame.status = FrameStatus.PENDING
                frame.save(update_fields=["status"])
                c = Copy.objects.filter(frame=frame, present=True).first()
                if c is not None:
                    enqueue(
                        catalogue_frame,
                        frame.sha256,
                        c.library_id,
                        c.rel_path,
                        dedupe_key=f"catalogue:{frame.sha256}",
                        priority=PRIORITY_BULK + 1,
                    )
            else:
                frame.status = FrameStatus.ERROR if frame.error else FrameStatus.CATALOGUED
                frame.save(update_fields=["status"])
                from apps.ingest.resolve import resolve_frame

                _, new_ds = resolve_frame(frame)
                if new_ds is not None:
                    touched[new_ds.pk] = new_ds
        if old_ds is not None:
            touched[old_ds.pk] = old_ds
        emit("frame.updated", {"sha256": frame.sha256, "fields": ["status"]})
        changed += 1
    for d in touched.values():
        touch_dataset(d)
    if touched:
        # the session medians changed with the frames that left or joined: grade those datasets again (a processed
        # copy set aside once dragged a session's background median down and every real sub looked "moonlit")
        from apps.processing.grading import regrade_datasets

        enqueue(
            regrade_datasets,
            sorted(touched),
            dedupe_key=f"regrade:{','.join(map(str, sorted(touched)))[:400]}",
        )
    return changed


def frames_for_rule(rule: IgnoreRule) -> list[Frame]:
    if rule.kind == IgnoreKind.CONTENT:
        return list(Frame.objects.filter(pk=rule.value))
    copies = Copy.objects.filter(present=True)
    if rule.library_id is not None:
        copies = copies.filter(library_id=rule.library_id)
    if rule.kind == IgnoreKind.FOLDER and rule.value.strip("/"):
        copies = copies.filter(rel_path__startswith=rule.value.strip("/") + "/")
    shas = {
        c.frame_id
        for c in copies.only("frame_id", "rel_path")
        if path_rule_matches(rule.kind, rule.value, c.rel_path)
    }
    return list(Frame.objects.filter(pk__in=shas))


def matching_files(rule: IgnoreRule) -> int:
    """Known files the rule covers (present copies)."""
    if rule.kind == IgnoreKind.CONTENT:
        return Copy.objects.filter(frame_id=rule.value, present=True).count()
    copies = Copy.objects.filter(present=True)
    if rule.library_id is not None:
        copies = copies.filter(library_id=rule.library_id)
    if rule.kind == IgnoreKind.FOLDER and rule.value.strip("/"):
        copies = copies.filter(rel_path__startswith=rule.value.strip("/") + "/")
    return sum(
        1
        for rel in copies.values_list("rel_path", flat=True)
        if path_rule_matches(rule.kind, rule.value, rel)
    )
