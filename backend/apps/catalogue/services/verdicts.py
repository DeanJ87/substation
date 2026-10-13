"""NINA thumbs-down (T064): NINA marks a rejected sub by renaming it with a `BAD_` prefix, and sync tools
often leave the un-prefixed twin beside it. Either way the content is one frame, and the prefix is the
user's decision: one REJECT verdict per frame, kept even if the BAD_ file later disappears (constitution III).
"""

from __future__ import annotations

from django.db import transaction

from ..models import (
    Copy,
    Frame,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    UserVerdict,
    Verdict,
    VerdictSource,
)


def apply_bad_prefix(frame: Frame) -> bool:
    """Record the NINA verdict for any BAD_ copy and keep the twinless item current. Idempotent.
    Returns True if the frame's verdicts changed."""
    copies = list(Copy.objects.filter(frame=frame))
    bad = [c for c in copies if c.is_bad_prefixed]
    changed = False
    with transaction.atomic():
        if bad and not UserVerdict.objects.filter(frame=frame, source=VerdictSource.NINA_BAD_PREFIX).exists():
            UserVerdict.objects.create(
                frame=frame, verdict=Verdict.REJECT, source=VerdictSource.NINA_BAD_PREFIX, copy=bad[0]
            )
            changed = True
        present = [c for c in copies if c.present]
        twinless = bool(present) and all(c.is_bad_prefixed for c in present)
        open_item = ReconciliationItem.objects.filter(
            frame=frame, kind=ReconciliationKind.BAD_WITHOUT_TWIN, status=ReconciliationStatus.OPEN
        )
        if twinless and not open_item.exists():
            ReconciliationItem.objects.create(
                frame=frame,
                dataset_id=frame.dataset_id,
                kind=ReconciliationKind.BAD_WITHOUT_TWIN,
                reason=(
                    f"{present[0].rel_path.rsplit('/', 1)[-1]} has no un-prefixed copy. It is treated as "
                    "rejected in NINA, like every BAD_ file."
                ),
            )
        elif not twinless:
            open_item.update(status=ReconciliationStatus.RESOLVED)
    return changed
