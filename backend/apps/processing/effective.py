"""Effective verdicts (spec 003 FR-005): the latest human decision (NINA BAD_ or an in-app override) if any,
unless the latest is "revert to auto"; otherwise the machine grade. And the dataset counts built from them."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.catalogue.models import Dataset, DatasetState, Frame, FrameStatus, FrameType, UserVerdict, Verdict

from .models import CalibrationMatch, MachineGrade, MatchState

HUMAN_TO_EFFECTIVE: dict[str, str] = {
    Verdict.ACCEPT: "accept",
    Verdict.KEEP: "down",
    Verdict.REJECT: "reject",
}


@dataclass
class Effective:
    verdict: str | None  # accept, down, reject, or None (not graded yet)
    manual: bool  # decided by a person (NINA or an override)
    source: str  # "machine", "nina", "override"
    weight: float


def human(verdicts: list[UserVerdict]) -> UserVerdict | None:
    latest = max(verdicts, key=lambda v: (v.created_at, v.pk), default=None)
    if latest is None or latest.verdict == Verdict.AUTO:
        return None
    return latest


def effective(
    frame: Frame, verdicts: list[UserVerdict] | None = None, grade: MachineGrade | None = None
) -> Effective:
    vs = verdicts if verdicts is not None else list(frame.verdicts.all())
    h = human(vs)
    if h is not None:
        src = "nina" if h.source == "nina_bad_prefix" else "override"
        g = grade if grade is not None else MachineGrade.objects.filter(frame=frame).first()
        weight = (
            0.0 if h.verdict == Verdict.REJECT else (g.weight if g and h.verdict == Verdict.KEEP else 1.0)
        )
        return Effective(HUMAN_TO_EFFECTIVE[h.verdict], True, src, weight)
    g = grade if grade is not None else MachineGrade.objects.filter(frame=frame).first()
    if g is None:
        return Effective(None, False, "machine", 1.0)
    return Effective(g.verdict, False, "machine", g.weight)


def recount_grades(ds: Dataset) -> None:
    lights = list(
        Frame.objects.filter(dataset=ds, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED)
        .prefetch_related("verdicts")
        .select_related("grade")
    )
    counts = {"accept": 0, "down": 0, "reject": 0}
    accepted_s = rejected_s = 0.0
    manual = 0
    for f in lights:
        try:
            g = f.grade
        except MachineGrade.DoesNotExist:
            g = None
        e = effective(f, list(f.verdicts.all()), g)
        if e.verdict:
            counts[e.verdict] += 1
            if e.verdict in ("accept", "down"):
                accepted_s += f.exptime_s or 0
            else:
                rejected_s += f.exptime_s or 0
        manual += e.source == "override"
    awaiting = CalibrationMatch.objects.filter(frame__in=lights, state=MatchState.AWAITING)
    ds.accepted_count, ds.down_count, ds.rejected_count = counts["accept"], counts["down"], counts["reject"]
    ds.awaiting_count = awaiting.count()
    ds.accepted_integration_s = accepted_s
    ds.rejected_integration_s = rejected_s
    ds.manual_count = manual
    fields = [
        "accepted_count",
        "down_count",
        "rejected_count",
        "awaiting_count",
        "accepted_integration_s",
        "rejected_integration_s",
        "manual_count",
    ]
    if ds.state in (DatasetState.OK, DatasetState.AWAITING_CALIBRATION):
        if ds.awaiting_count:
            first = awaiting.first()
            ds.state = DatasetState.AWAITING_CALIBRATION
            n = ds.awaiting_count
            reason = first.reason.removeprefix("Awaiting calibration: ") if first else ""
            ds.state_reason = f"{n} sub{'s' if n != 1 else ''} waiting for calibration: {reason}"
        else:
            ds.state, ds.state_reason = DatasetState.OK, ""
        fields += ["state", "state_reason"]
    ds.save(update_fields=fields)
    from .masters import check_stale

    check_stale(ds)


def flagged(qs):  # noqa: ANN001, ANN201
    """Subs to review (spec 003 A2): rejected, down-weighted or near a threshold, by machine or human."""
    return qs.filter(Q(grade__verdict__in=["reject", "down"]) | Q(grade__near_threshold=True))
