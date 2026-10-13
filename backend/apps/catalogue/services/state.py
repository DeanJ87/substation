"""Dataset state (T066): a dataset needs reconciliation while any open, non-informational item points at it
or at one of its frames, with a plain-English reason (voice guide)."""

from __future__ import annotations

from django.db.models import Count, Q

from ..models import (
    Dataset,
    DatasetState,
    Frame,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
)

INFORMATIONAL = {ReconciliationKind.BAD_WITHOUT_TWIN}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def update_state(ds: Dataset) -> None:
    frames = Frame.objects.filter(dataset=ds)
    items = (
        ReconciliationItem.objects.filter(status=ReconciliationStatus.OPEN)
        .filter(Q(dataset=ds) | Q(frame__in=frames))
        .exclude(kind__in=INFORMATIONAL)
    )
    by_kind = dict(items.values_list("kind").annotate(n=Count("id", distinct=True)))
    missing = by_kind.get(ReconciliationKind.FRAME_MISSING, 0)  # dismissing the item accepts the loss
    reasons = []
    if missing:
        reasons.append(f"{_plural(missing, 'file is', 'files are')} missing from disk.")
    other = sum(n for k, n in by_kind.items() if k != ReconciliationKind.FRAME_MISSING)
    if other:
        reasons.append(f"{_plural(other, 'value needs', 'values need')} checking.")
    if reasons:
        state, reason = DatasetState.NEEDS_RECONCILIATION, " ".join(reasons) + " Review before stacking."
    elif ds.state == DatasetState.NEEDS_RECONCILIATION:
        state, reason = DatasetState.OK, ""
    else:
        return
    if (ds.state, ds.state_reason) != (state, reason):
        ds.state, ds.state_reason = state, reason
        ds.save(update_fields=["state", "state_reason"])
