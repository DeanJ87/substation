"""Changes made by hand, and undoing them (spec 016)."""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Change, Dataset, Frame, UserVerdict

UNDO_FOR_DAYS = 30


class CantUndo(Exception):
    """Said plainly, for the page."""


def record(user, kind: str, summary: str, count: int, **data) -> Change:  # noqa: ANN001
    return Change.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        kind=kind,
        summary=summary[:200],
        count=count,
        data=data,
    )


def _touch(dataset_ids: Iterable[int]) -> None:
    from apps.catalogue.services.tracking import touch_dataset
    from apps.processing.effective import recount_grades

    for ds in Dataset.objects.filter(pk__in=set(dataset_ids)):
        recount_grades(ds)
        touch_dataset(ds)


def undo(change: Change) -> str:
    """Reverse one change; returns what happened, as a sentence."""
    if change.undone_at is not None:
        raise CantUndo("That change was already undone.")
    if (timezone.now() - change.created_at).days > UNDO_FOR_DAYS:
        raise CantUndo(f"Changes can be undone for {UNDO_FOR_DAYS} days; this one is older.")
    with transaction.atomic():
        if change.kind in (Change.Kind.VERDICT, Change.Kind.AGREE):
            rows = UserVerdict.objects.filter(pk__in=change.data.get("verdict_ids", []))
            frames = list(Frame.objects.filter(verdicts__in=rows).distinct().values_list("pk", "dataset_id"))
            rows.delete()
            _touch(ds for _, ds in frames if ds)
            from substation.events.emit import emit

            for sha, _ in frames:
                emit("frame.updated", {"sha256": sha, "fields": ["verdict"]})
            note = f"Undone: {change.summary[:1].lower()}{change.summary[1:]}"
        elif change.kind == Change.Kind.BIN:
            from apps.catalogue.services.binning import restore_frames

            out = restore_frames(change.data.get("sha256s", []))
            note = f"Restored {out['restored']:,} from the bin"
            if out["not_restored"]:
                note += f"; {out['not_restored']:,} couldn't be put back"
        else:
            raise CantUndo("This kind of change can't be undone.")
        Change.objects.filter(pk=change.pk).update(undone_at=timezone.now())
    return note + "."
