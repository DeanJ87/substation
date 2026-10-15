"""What to shoot (spec 017): the lights waiting for calibration, grouped into the darks, biases and flats that
would release them, with how much each would unlock. Darks and biases can be shot by a sequence; flats belong to
the rig as it was on the night, so they're listed for the owner to shoot, never scheduled."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from xml.sax.saxutils import escape

from apps.catalogue.models import Frame

from .matching import dims
from .models import CalibrationMatch, MatchState

FRAMES = 30  # a sensible master: enough frames to beat down read noise without a long session


@dataclass
class Need:
    kind: str  # dark | bias | flat
    camera: str
    exptime_s: float | None = None
    gain: int | None = None
    offset: int | None = None
    xbin: int = 1
    temp_c: float | None = None  # the set point to cool to; None for an uncooled camera
    size: str = ""
    filter: str = ""
    telescope: str = ""
    subs: int = 0
    integration_s: float = 0.0
    nights: set[date] = field(default_factory=set)
    datasets: dict[int, str] = field(default_factory=dict)


@dataclass
class Other:
    reason: str
    subs: int = 0
    datasets: dict[int, str] = field(default_factory=dict)


def _temp(f: Frame) -> float | None:
    if f.set_temp_c is not None:
        return float(f.set_temp_c)
    return float(round(f.ccd_temp_c)) if f.ccd_temp_c is not None else None


def _kind(m: CalibrationMatch) -> list[str]:
    """What this waiting light needs shot: dark, bias and/or flat; [] when it waits for something else."""
    reason = m.reason or ""
    out = []
    if m.dark_id is None and "master bias" in reason:
        out.append("bias")
    elif (
        m.dark_id is None and " dark" in reason and "Reconcile" not in reason and "bias is raw" not in reason
    ):
        out.append("dark")
    if m.flat_id is None and " flat" in reason and "to be built" not in reason:
        out.append("flat")
    return out


def _key(kind: str, f: Frame) -> tuple:
    size = "×".join(map(str, dims(f) or ()))
    if kind == "flat":
        return (kind, f.camera or "", f.telescope or "", f.filter_norm or "", f.xbin or 1, size)
    if kind == "bias":
        return (kind, f.camera or "", f.gain, f.offset, f.xbin or 1, size)
    return (kind, f.camera or "", f.exptime_s, f.gain, f.offset, f.xbin or 1, _temp(f), size)


def shopping_list() -> tuple[list[Need], list[Other]]:
    needs: dict[tuple, Need] = {}
    others: dict[str, Other] = defaultdict(lambda: Other(""))
    rows = CalibrationMatch.objects.filter(state=MatchState.AWAITING).select_related(
        "frame", "frame__night", "frame__dataset"
    )
    for m in rows.prefetch_related("frame__headers"):
        f = m.frame
        label = f.dataset.display_name if f.dataset else ""
        kinds = _kind(m)
        if not kinds:
            why = (m.reason or "Waiting").removeprefix("Awaiting calibration: ").rstrip(".")
            o = others[why]
            o.reason, o.subs = why, o.subs + 1
            if f.dataset_id:
                o.datasets[f.dataset_id] = label
            continue
        for kind in kinds:
            k = _key(kind, f)
            n = needs.get(k)
            if n is None:
                n = needs[k] = Need(
                    kind=kind,
                    camera=f.camera or "",
                    exptime_s=f.exptime_s if kind == "dark" else None,
                    gain=f.gain if kind != "flat" else None,
                    offset=f.offset if kind != "flat" else None,
                    xbin=f.xbin or 1,
                    temp_c=_temp(f) if kind == "dark" else None,
                    size=k[-1],
                    filter=f.filter_norm or "" if kind == "flat" else "",
                    telescope=f.telescope or "" if kind == "flat" else "",
                )
            n.subs += 1
            n.integration_s += f.exptime_s or 0
            if f.night_id and f.night:
                n.nights.add(f.night.date)
            if f.dataset_id:
                n.datasets[f.dataset_id] = label
    order = {"dark": 0, "bias": 1, "flat": 2}
    return (
        sorted(needs.values(), key=lambda n: (order[n.kind], -n.subs)),
        sorted(others.values(), key=lambda o: -o.subs),
    )


def nina_darks_xml(needs: list[Need], frames: int = FRAMES) -> str:
    """The darks and biases as a NINA sequence (the simple sequencer's target file). NINA can't set the cooling per
    row, so rows are ordered by temperature, with the set point in each row's comment."""
    rows = sorted(
        (n for n in needs if n.kind in ("dark", "bias")),
        key=lambda n: (n.temp_c if n.temp_c is not None else 99, n.camera, n.exptime_s or 0),
    )
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!-- Calibration frames SubStation is waiting for. Cool the camera to each row's temperature first. -->",
        '<CaptureSequenceList xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" TargetName="SubStation calibration" '
        'Mode="STANDARD" Delay="0" SlewToTarget="false" AutoFocusOnStart="false" CenterTarget="false" '
        'StartGuiding="false">',
    ]
    for n in rows:
        cool = f"{n.temp_c:g} °C" if n.temp_c is not None else "any temperature"
        what = "bias" if n.kind == "bias" else f"{n.exptime_s:g} s dark"
        out += [
            f"  <!-- {escape(n.camera)}: {what} at {cool}; releases {n.subs} sub{'s' if n.subs != 1 else ''} -->",
            "  <CaptureSequence>",
            "    <Enabled>true</Enabled>",
            f"    <ExposureTime>{0 if n.kind == 'bias' else n.exptime_s:g}</ExposureTime>",
            f"    <ImageType>{'BIAS' if n.kind == 'bias' else 'DARK'}</ImageType>",
            '    <FilterType xsi:nil="true" />',
            f"    <Binning><X>{n.xbin}</X><Y>{n.xbin}</Y></Binning>",
            f"    <Gain>{n.gain if n.gain is not None else -1}</Gain>",
            f"    <Offset>{n.offset if n.offset is not None else -1}</Offset>",
            f"    <TotalExposureCount>{frames}</TotalExposureCount>",
            "    <ProgressExposureCount>0</ProgressExposureCount>",
            "    <Dither>false</Dither>",
            "    <DitherAmount>1</DitherAmount>",
            "  </CaptureSequence>",
        ]
    out.append("</CaptureSequenceList>")
    return "\n".join(out) + "\n"


def csv_text(needs: list[Need], frames: int = FRAMES) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "kind",
            "camera",
            "telescope",
            "filter",
            "exposure_s",
            "gain",
            "offset",
            "binning",
            "temperature_c",
            "size",
            "frames",
            "subs_waiting",
            "nights",
        ]
    )
    for n in needs:
        w.writerow(
            [
                n.kind,
                n.camera,
                n.telescope,
                n.filter,
                "" if n.exptime_s is None else f"{n.exptime_s:g}",
                "" if n.gain is None else n.gain,
                "" if n.offset is None else n.offset,
                n.xbin,
                "" if n.temp_c is None else f"{n.temp_c:g}",
                n.size,
                frames if n.kind != "flat" else "",
                n.subs,
                " ".join(d.isoformat() for d in sorted(n.nights)),
            ]
        )
    return buf.getvalue()
