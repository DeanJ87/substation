"""Metadata resolution (research R8; T074). Every field's value comes from somewhere, and that is recorded:

1. a user value for this content (always wins)
2. path patterns that list the field in `prefer_over_header` (most specific scope first, then priority)
3. the header
4. other matching path patterns
5. inference, then installation settings

`resolve_frame` works from stored header values, so a pattern change or a correction re-resolves a frame
without reading its file. It sets the resolved fields, classification, night and dataset, records header vs
pattern conflicts, and keeps the frame's reconciliation items current.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import Count

from apps.catalogue.models import (
    ClassificationSource,
    ContentCorrection,
    Copy,
    Dataset,
    Frame,
    FrameStatus,
    FrameType,
    HeaderConflict,
    MetadataSource,
    MetadataValue,
    PathPattern,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
)
from apps.catalogue.services.calibration_sets import (
    assign_calibration_set,
    flat_set_for_dark,
    recheck_darks_for,
    recount,
)
from apps.catalogue.services.grouping import assign_dataset, night_for, split_object
from apps.libraries.models import InstallationSettings, Library

from .classify import classify_type
from .fields import FieldValue, normalise_filter
from .night import observing_night, parse_date_obs
from .patterns import PatternError, compile_pattern, match

# MetadataValue.field -> Frame resolved attribute
RESOLVED_ATTR = {
    "object": "object",
    "filter": "filter_raw",
    "exptime": "exptime_s",
    "ccd_temp": "ccd_temp_c",
    "set_temp": "set_temp_c",
    "gain": "gain",
    "offset": "offset",
    "xbin": "xbin",
    "ybin": "ybin",
    "camera": "camera",
    "telescope": "telescope",
    "date_obs": "date_obs_utc",
    "site_lat": "site_lat",
    "site_lon": "site_lon",
}
FLOAT_ATTRS = {"exptime_s", "ccd_temp_c", "set_temp_c", "site_lat", "site_lon"}
INT_ATTRS = {"gain", "offset", "xbin", "ybin", "panel"}
PATTERN_SOURCES = (MetadataSource.FOLDER_PATTERN, MetadataSource.FILENAME_PATTERN)

# Fields a frame needs before it can be used (missing_field items); per type
REQUIRED: dict[str, tuple[str, ...]] = {
    FrameType.LIGHT: ("target", "filter", "exptime", "date_obs"),
    FrameType.FLAT: ("filter", "exptime"),
    FrameType.DARK: ("exptime",),
    FrameType.DARK_FLAT: ("exptime",),
}
FIELD_NAMES = {
    "target": "target",
    "filter": "filter",
    "exptime": "exposure time",
    "date_obs": "observation time",
    "frame_type": "frame type",
}


def _text(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def record_header_values(frame: Frame, values: dict[str, FieldValue]) -> None:
    frame.metadata.filter(source__in=[MetadataSource.HEADER, MetadataSource.INFERRED]).delete()
    MetadataValue.objects.bulk_create(
        [
            MetadataValue(
                frame=frame,
                field=f,
                value=_text(v.value),
                raw=v.raw[:500],
                source=MetadataSource.INFERRED
                if v.source_detail.startswith("inferred")
                else MetadataSource.HEADER,
                source_detail=v.source_detail.removeprefix("inferred: "),
            )
            for f, v in values.items()
        ]
    )


@dataclass
class _Pattern:
    row: PathPattern
    compiled: Any

    @property
    def specificity(self) -> tuple[int, int, int]:
        literal = len(self.row.scope_glob.replace("*", ""))
        return (self.row.library_id is not None, literal, self.row.priority)


def _patterns_for(library_ids: set[int]) -> list[_Pattern]:
    out = []
    for p in PathPattern.objects.filter(enabled=True):
        if p.library_id is not None and p.library_id not in library_ids:
            continue
        try:
            out.append(_Pattern(p, compile_pattern(p.pattern, p.kind)))
        except PatternError:
            continue  # the editor refuses these; an old one that no longer compiles is just skipped
    out.sort(key=lambda p: p.specificity, reverse=True)
    return out


def _in_scope(p: PathPattern, copy: Copy) -> bool:
    if p.library_id is not None and p.library_id != copy.library_id:
        return False
    glob = p.scope_glob or "**"
    return glob in ("**", "*") or fnmatch.fnmatchcase(copy.rel_path, glob)


def _site_lon(frame: Frame, library: Library | None, settings_row: InstallationSettings) -> float | None:
    if frame.site_lon is not None:
        return frame.site_lon
    if library is not None and library.site_lon is not None:
        return library.site_lon
    return settings_row.site_lon


def _record_pattern_values(
    frame: Frame, copies: list[Copy], header_lon: float | None, settings_row: InstallationSettings
) -> list[_Pattern]:
    """Rebuild this frame's pattern values from its present copies. Returns the patterns used, in order."""
    frame.metadata.filter(source__in=PATTERN_SOURCES).delete()
    patterns = _patterns_for({c.library_id for c in copies})
    rows, used = [], []
    libs = {lib.pk: lib for lib in Library.objects.filter(pk__in={c.library_id for c in copies})}
    for p in patterns:
        for c in copies:
            if not _in_scope(p.row, c):
                continue
            lon = header_lon
            if lon is None:
                lib = libs.get(c.library_id)
                lon = lib.site_lon if lib is not None and lib.site_lon is not None else settings_row.site_lon
            got = match(p.compiled, c.rel_path, site_lon=lon)
            if not got:
                continue
            src = MetadataSource.FOLDER_PATTERN if p.row.kind == "folder" else MetadataSource.FILENAME_PATTERN
            for f, v in got.items():
                rows.append(
                    MetadataValue(
                        frame=frame,
                        field=f,
                        value=_text(v),
                        raw=_text(v),
                        source=src,
                        source_detail=f"pattern #{p.row.pk}",
                    )
                )
            used.append(p)
            break  # one copy per pattern is enough
    MetadataValue.objects.bulk_create(rows, ignore_conflicts=True)
    return used


def _sync_user_values(frame: Frame) -> None:
    """Content corrections (which outlive copies, and apply to identical content found later) as user rows."""
    corrections = {c.field: c for c in ContentCorrection.objects.filter(sha256=frame.sha256)}
    frame.metadata.filter(source=MetadataSource.USER).exclude(field__in=corrections).delete()
    have = set(frame.metadata.filter(source=MetadataSource.USER).values_list("field", flat=True))
    for f, c in corrections.items():
        if f in have:
            frame.metadata.filter(source=MetadataSource.USER, field=f).update(
                value=c.value, raw=c.value, user=c.user
            )
        else:
            MetadataValue.objects.create(
                frame=frame, field=f, value=c.value, raw=c.value, source=MetadataSource.USER, user=c.user
            )


def _rank(mv: MetadataValue, prefer: dict[str, set[str]], order: dict[str, int]) -> tuple[int, int]:
    if mv.source == MetadataSource.USER:
        return (0, 0)
    if mv.source in PATTERN_SOURCES:
        pos = order.get(mv.source_detail, 999)
        return (1, pos) if mv.field in prefer.get(mv.source_detail, set()) else (3, pos)
    if mv.source == MetadataSource.HEADER:
        return (2, 0)
    return (4, 0) if mv.source == MetadataSource.INFERRED else (5, 0)


def _coerce(attr: str, v: str | None) -> Any:
    if v is None or v == "":
        return None
    try:
        if attr in FLOAT_ATTRS:
            return float(v)
        if attr in INT_ATTRS:
            return int(float(v))
    except ValueError:
        return None
    if attr == "date_obs_utc":
        return parse_date_obs(v)
    return v


def _source_label(mv: MetadataValue | None) -> str:
    if mv is None:
        return "header"
    if mv.source == MetadataSource.HEADER:
        return mv.source_detail or "header"
    if mv.source in PATTERN_SOURCES:
        return f"{'folder' if mv.source == MetadataSource.FOLDER_PATTERN else 'file name'} {mv.source_detail}"
    if mv.source == MetadataSource.USER:
        return "your correction"
    return mv.source


def _pick_winners(frame: Frame, prefer: dict, order: dict) -> dict[str, MetadataValue]:
    """The winning value of each field; disagreements between sources are kept as conflicts to show."""
    by_field: dict[str, list[MetadataValue]] = {}
    for mv in frame.metadata.all():
        by_field.setdefault(mv.field, []).append(mv)
    winners: dict[str, MetadataValue] = {}
    for f, cands in by_field.items():
        cands = [c for c in cands if c.value not in (None, "")]
        if not cands:
            continue
        winners[f] = min(cands, key=lambda mv: _rank(mv, prefer, order))
        # Header and patterns disagreeing is worth showing, whichever wins
        found = {f"{c.source}:{c.source_detail}": c.value for c in cands if c.source != MetadataSource.USER}
        if len({_norm(f, v) for v in found.values()}) > 1:
            HeaderConflict.objects.update_or_create(frame=frame, field=f, defaults={"values": found})
        else:
            HeaderConflict.objects.filter(frame=frame, field=f).delete()
    win_ids = [w.pk for w in winners.values()]
    HeaderConflict.objects.filter(frame=frame).exclude(field__in=winners).delete()
    frame.metadata.exclude(pk__in=win_ids).update(is_winner=False)
    frame.metadata.filter(pk__in=win_ids).update(is_winner=True)
    return winners


def _apply_equipment_names(frame: Frame, eq: dict) -> None:
    # a rig merge maps one exact camera + telescope pair onto another, so the same telescope name used with a
    # different camera is left alone; the older name-only maps still apply
    pair = eq.get("rig", {}).get(f"{frame.camera or ''}|{frame.telescope or ''}")
    if pair:
        frame.camera, frame.telescope = pair[0] or None, pair[1] or None
    else:
        frame.camera = eq.get("camera", {}).get(frame.camera or "", frame.camera)
        frame.telescope = eq.get("telescope", {}).get(frame.telescope or "", frame.telescope)


def _apply_target(frame: Frame, winners: dict[str, MetadataValue], eq: dict) -> None:
    frame.target, frame.panel = split_object(frame.object)
    if "target" in winners:  # a target given directly (pattern or user) beats one split from OBJECT
        frame.target = winners["target"].value
        if "panel" not in winners and "object" not in winners:
            frame.panel = None
    if "panel" in winners:
        frame.panel = _coerce("panel", winners["panel"].value)
    if frame.target:  # names merged into another (Library → collection → Merge names)
        frame.target = eq.get("target", {}).get(frame.target, frame.target)


_CLASSIFIED_BY: dict[str, str] = {
    MetadataSource.USER: ClassificationSource.USER,
    MetadataSource.FOLDER_PATTERN: ClassificationSource.PATH_PATTERN,
    MetadataSource.FILENAME_PATTERN: ClassificationSource.PATH_PATTERN,
}


def _classify(
    frame: Frame, winners: dict[str, MetadataValue], copies: list[Copy], has_integration: bool | None
) -> None:
    """Frame type and where it came from; then the checks that catch a header's wrong type (not your own)."""
    integ = frame.integration_index is not None if has_integration is None else has_integration
    ft = winners.get("frame_type")
    frame.frame_type, frame.classification_reason = classify_type(
        ft.value if ft else None, _source_label(ft), integ
    )
    frame.classification_source = _CLASSIFIED_BY.get(ft.source if ft else "", ClassificationSource.HEADER)
    if frame.classification_source == ClassificationSource.USER:
        return
    # each check looks at the type as the one before left it: a "light" found to be a dark gets the dark rules
    if frame.frame_type == FrameType.LIGHT and frame.classification_source == ClassificationSource.HEADER:
        _mislabelled_calibration(frame, copies)
    if frame.frame_type == FrameType.LIGHT:
        _already_processed(frame)
    if frame.frame_type == FrameType.LIGHT:
        _already_stacked(frame)
    if frame.frame_type == FrameType.DARK:
        _dark_flat_rules(frame)


def resolve_frame(frame: Frame, has_integration: bool | None = None) -> tuple[Dataset | None, Dataset | None]:
    """Resolve every field, then classify, place in a night and dataset, and update reconciliation items.
    Sets attributes on `frame` and saves it. Returns (old dataset, new dataset) for recounting."""
    settings_row = InstallationSettings.load()
    copies = list(Copy.objects.filter(frame=frame, present=True).select_related("library").order_by("pk"))
    header_lon = _coerce(
        "site_lon",
        frame.metadata.filter(source=MetadataSource.HEADER, field="site_lon")
        .values_list("value", flat=True)
        .first(),
    )
    used = _record_pattern_values(frame, copies, header_lon, settings_row)
    _sync_user_values(frame)
    prefer = {f"pattern #{p.row.pk}": set(p.row.prefer_over_header or []) for p in used}
    order = {f"pattern #{p.row.pk}": i for i, p in enumerate(used)}

    winners = _pick_winners(frame, prefer, order)

    def val(f: str) -> str | None:
        return winners[f].value if f in winners else None

    for f, attr in RESOLVED_ATTR.items():
        setattr(frame, attr, _coerce(attr, val(f)))
    from apps.processing.config import processing_settings

    eq = processing_settings().get("equipment", {})
    _apply_equipment_names(frame, eq)
    _apply_target(frame, winners, eq)
    frame.filter_norm = normalise_filter(frame.filter_raw, settings_row.filter_aliases or {})

    frame.night = _night(frame, copies[0].library if copies else None, settings_row)
    if frame.status != FrameStatus.ERROR:
        _classify(frame, winners, copies, has_integration)

    old, new = assign_dataset(frame)
    old_cs, new_cs = assign_calibration_set(frame)
    frame.save()
    for cs in {c for c in (old_cs, new_cs) if c is not None}:
        if recount(cs) and cs.type == FrameType.FLAT and cs is new_cs:
            recheck_darks_for(cs)  # a flat set formed or grew: matching darks are dark flats
    _update_items(frame, winners, copies)
    from apps.processing.tasks import after_resolve

    after_resolve(frame)
    return old, new


_CAL_WORDS = {
    "darkflat": FrameType.DARK_FLAT,
    "flatdark": FrameType.DARK_FLAT,
    "dark": FrameType.DARK,
    "flat": FrameType.FLAT,
    "bias": FrameType.BIAS,
    "offset": FrameType.BIAS,
}


def _cal_word(text: str) -> FrameType | None:
    key = re.sub(r"[\s\-_]", "", text.casefold())
    for word, t in _CAL_WORDS.items():  # longest first: dark flat before dark
        if key.startswith(word):
            return t
    return None


_PROCESSING_MARKS = ("PCL:Signature:Calibration", "PCL:Signature:Registration", "PCL:Signature:Debayer")
_PROCESSING_HISTORY = re.compile(r"\b(ImageCalibration|StarAlignment|Debayer|LocalNormalization)\b")


def _already_processed(frame: Frame) -> None:
    """A light another program has already calibrated, registered or debayered (owner 2026-10-11: WBPP's
    calibrated/_c and registered/_r copies were catalogued beside the raw subs, doubling sessions and wrecking the
    session stretch). PixInsight signs its output in XISF properties; FITS output keeps HISTORY lines."""
    for h in frame.headers.all():
        props = h.properties or {}
        mark = next((m for m in _PROCESSING_MARKS if m in props), None)
        if mark is None:
            history = " ".join(
                str(v.get("value", v) if isinstance(v, dict) else v)
                for k, v in (h.keywords or {}).items()
                if k.upper().startswith("HISTORY")
            )
            found = _PROCESSING_HISTORY.search(history)
            mark = found.group(1) if found else None
        if mark:
            frame.frame_type = FrameType.PROCESSED
            frame.classification_source = ClassificationSource.RULE
            step = mark.rsplit(":", 1)[-1]
            frame.classification_reason = f"Already processed by other software ({step}): not a raw sub."
            return


def stack_count(keywords: dict) -> int:
    """How many subs a file says it holds (Seestar's STACKCNT, or NCOMBINE); 1 for a single sub."""
    for k in ("STACKCNT", "NCOMBINE"):
        v = keywords.get(k)
        v = v.get("value") if isinstance(v, dict) else v
        try:
            if v is not None and int(float(v)) > 1:
                return int(float(v))
        except (TypeError, ValueError):
            continue
    return 1


def _already_stacked(frame: Frame) -> None:
    """A light that is already a stack of many subs: a Seestar writes its own running stack (Stacked_153_….fit,
    STACKCNT 153) beside the subs, with IMAGETYP Light and the subs' exposure. As a sub it was graded with them and
    put into SubStation's own stacks (IC 4605, 2026-10-14: a 4320×7680 mosaic among 2160×3840 subs crashed Siril's
    plate solving). It is a master light, not a sub."""
    for h in frame.headers.all():
        n = stack_count(h.keywords or {})
        if n > 1:
            frame.frame_type = FrameType.MASTER_LIGHT
            frame.classification_source = ClassificationSource.RULE
            frame.classification_reason = f"A stack of {n} subs made by the capture software: not a sub."
            return


def _mislabelled_calibration(frame: Frame, copies: list) -> None:  # noqa: ANN001
    """A capture program left on Light while shooting darks (owner 2026-10-11: 30 A7 III darks in
    _CalibrationFrames/…/Darks/ named Dark_180s_… with IMAGETYP 'Light Frame'). When a folder on the path and the
    file name both name the same calibration type, that wins over the header, and the reason says so."""
    for c in copies:
        parts = c.rel_path.split("/")
        by_name = _cal_word(parts[-1])
        if by_name is None or not any(_cal_word(d) == by_name for d in parts[:-1]):
            continue
        frame.frame_type = by_name
        frame.classification_source = ClassificationSource.RULE
        frame.classification_reason = (
            f"Header says Light, but the folder and file name say {by_name.label.lower()} ({parts[-1]})."
        )
        return


def _dark_flat_rules(frame: Frame) -> None:
    """Darks that are really dark flats (T094, T095): NINA's flat wizard marks them OBJECT 'FlatWizard'; and a
    dark at the exposure of a flat set taken the same night is one too."""
    if (frame.object or "").strip().casefold() == "flatwizard":
        frame.frame_type = FrameType.DARK_FLAT
        frame.classification_source = ClassificationSource.RULE
        frame.classification_reason = "IMAGETYP = 'DARK', OBJECT 'FlatWizard': NINA dark flat."
        return
    flats = flat_set_for_dark(frame)
    if flats is not None:
        frame.frame_type = FrameType.DARK_FLAT
        frame.classification_source = ClassificationSource.RULE
        when = flats.session_start_utc.strftime("%-d %b")
        frame.classification_reason = (
            f"IMAGETYP = 'DARK' at {frame.exptime_s:g} s, matching the {flats.filter_norm or ''} flat set on "
            f"{when}."
        ).replace("the  flat", "the flat")


def _norm(field: str, v: str | None) -> str:
    if v is None:
        return ""
    if field == "filter":
        return (normalise_filter(v, {}) or "").casefold()
    try:
        return f"{float(v):g}"
    except ValueError:
        return v.strip().casefold()


def _night(frame: Frame, library: Library | None, settings_row: InstallationSettings):  # noqa: ANN202
    if frame.date_obs_utc is None:
        return None
    lat, lon = frame.site_lat, frame.site_lon
    if lon is None:
        if library is not None and library.site_lon is not None:
            lat, lon = library.site_lat, library.site_lon
        else:
            lat, lon = settings_row.site_lat, settings_row.site_lon
    if lon is None:
        return None
    return night_for(observing_night(frame.date_obs_utc, lon), lat, lon)


def _suggest(frame: Frame, field: str, copies: list[Copy]) -> dict | None:
    """The most common value of this field among other files in the same folder."""
    for c in copies:
        folder = os.path.dirname(c.rel_path)
        prefix = f"{folder}/" if folder else ""
        row = (
            MetadataValue.objects.filter(
                field=field,
                is_winner=True,
                frame__copies__library_id=c.library_id,
                frame__copies__rel_path__startswith=prefix,
            )
            .exclude(frame=frame)
            .values("value")
            .annotate(n=Count("frame", distinct=True))
            .order_by("-n")
            .first()
        )
        if row and row["value"]:
            where = f"{folder}/" if folder else "the top folder"
            return {
                "value": row["value"],
                "why": f"{row['n']} other files in {where} have {FIELD_NAMES.get(field, field)} {row['value']}.",
            }
    return None


def _update_items(frame: Frame, winners: dict[str, MetadataValue], copies: list[Copy]) -> None:
    have = set(winners) | ({"target"} if frame.target else set())
    if frame.status == FrameStatus.ERROR:
        required: tuple[str, ...] = ()
    else:
        required = REQUIRED.get(frame.frame_type, ())
    open_items = ReconciliationItem.objects.filter(frame=frame, status=ReconciliationStatus.OPEN)
    open_items.filter(kind=ReconciliationKind.MISSING_FIELD).exclude(
        field__in=[f for f in required if f not in have]
    ).update(status=ReconciliationStatus.RESOLVED, resolution={"by": "resolved"})
    name = os.path.basename(copies[0].rel_path) if copies else frame.sha256[:12]
    for f in required:
        if f in have:
            continue
        ReconciliationItem.objects.get_or_create(
            kind=ReconciliationKind.MISSING_FIELD,
            frame=frame,
            field=f,
            status=ReconciliationStatus.OPEN,
            defaults={
                "dataset_id": frame.dataset_id,
                "reason": f"No {FIELD_NAMES.get(f, f)} in the header of {name} or the path.",
                "suggestion": _suggest(frame, f, copies),
            },
        )
    _master_items(frame, winners, copies, name)
    unknown = frame.frame_type == FrameType.UNKNOWN and frame.status != FrameStatus.ERROR
    cls = open_items.filter(kind=ReconciliationKind.CLASSIFICATION_UNKNOWN)
    if unknown and not cls.exists():
        ReconciliationItem.objects.create(
            kind=ReconciliationKind.CLASSIFICATION_UNKNOWN,
            frame=frame,
            field="frame_type",
            reason=f"{name}: {frame.classification_reason}",
            suggestion=_suggest(frame, "frame_type", copies),
        )
    elif not unknown:
        cls.update(status=ReconciliationStatus.RESOLVED, resolution={"by": "resolved"})


MASTER_FIELDS = {"gain": "gain", "offset": "offset", "set_temp": "temperature"}
_PATH_HINTS = {
    "set_temp": re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*[cC](?![a-zA-Z])"),
    "gain": re.compile(r"(?i)(?:gain|\bg)[ _-]?(\d+)\b"),
    "offset": re.compile(r"(?i)(?:offset|\bo)[ _-]?(\d+)\b"),
}


def _master_suggestion(frame: Frame, field: str, copies: list[Copy]) -> dict | None:
    """From the path (`-20c` → set temperature −20), else from this camera's lights."""
    rx = _PATH_HINTS.get(field)
    for c in copies:
        m = rx.search(c.rel_path) if rx else None
        if m:
            return {"value": m.group(1), "why": f"The path {c.rel_path} says {m.group(0).strip()}."}
    attr = {"gain": "gain", "offset": "offset", "set_temp": "set_temp_c"}[field]
    row = (
        Frame.objects.filter(frame_type=FrameType.LIGHT, camera=frame.camera, **{f"{attr}__isnull": False})
        .values(attr)
        .annotate(n=Count("sha256"))
        .order_by("-n")
        .first()
    )
    if row:
        v = row[attr]
        v = f"{v:g}" if isinstance(v, float) else str(v)
        return {
            "value": v,
            "why": f"{row['n']} of your {frame.camera or ''} lights use {MASTER_FIELDS[field]} {v}.".replace(
                "  ", " "
            ),
        }
    return None


def _master_items(frame: Frame, winners: dict[str, MetadataValue], copies: list[Copy], name: str) -> None:
    """Masters without the values calibration matching needs (T096), and multi-image files where the master
    image can't be told apart (US6)."""
    from apps.catalogue.models import MASTER_TYPES

    is_master = frame.frame_type in MASTER_TYPES and frame.status == FrameStatus.CATALOGUED
    have = set(winners)
    if "ccd_temp" in have:
        have.add("set_temp")
    open_items = ReconciliationItem.objects.filter(frame=frame, status=ReconciliationStatus.OPEN)
    needed = [f for f in MASTER_FIELDS if is_master and f not in have]
    open_items.filter(kind=ReconciliationKind.MASTER_METADATA).exclude(field__in=needed).update(
        status=ReconciliationStatus.RESOLVED, resolution={"by": "resolved"}
    )
    for f in needed:
        ReconciliationItem.objects.get_or_create(
            kind=ReconciliationKind.MASTER_METADATA,
            frame=frame,
            field=f,
            status=ReconciliationStatus.OPEN,
            defaults={
                "reason": f"{name} has no {MASTER_FIELDS[f]} in its header, and calibration matching needs it.",
                "suggestion": _master_suggestion(frame, f, copies),
            },
        )
    ambiguous = (
        frame.image_count > 1 and frame.integration_index is None and frame.status == FrameStatus.CATALOGUED
    )
    amb = open_items.filter(kind=ReconciliationKind.AMBIGUOUS_MASTER)
    if ambiguous and not amb.exists():
        ReconciliationItem.objects.create(
            kind=ReconciliationKind.AMBIGUOUS_MASTER,
            frame=frame,
            reason=(
                f"{name} holds {frame.image_count} images and none is named 'integration', so SubStation "
                "can't tell which one is the master. Its first image is used for now."
            ),
        )
    elif not ambiguous:
        amb.update(status=ReconciliationStatus.RESOLVED, resolution={"by": "resolved"})
