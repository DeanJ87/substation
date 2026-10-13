"""Calibration QA and master building (spec 002 US2, US3).

`qa_calibration_set`: per-frame statistics against the set's robust median, a thumbnail for the contact sheet,
and a verdict with a plain-English reason. `build_master`: stack the frames that passed with Siril (darks, dark
flats and bias without normalisation; flats calibrated by the matching master dark flat or bias, then
multiplicatively normalised), register the result as a master SubStation built (provenance kept), and for flats
report falloff and dust motes. Built masters join matching like any other master.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path

import numpy as np
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import (
    CalibrationSet,
    Copy,
    Frame,
    FrameStatus,
    FrameType,
    MetadataSource,
    MetadataValue,
)
from apps.libraries.models import Library
from substation.events.emit import emit
from substation.tasks import PRIORITY_BULK, enqueue, report_progress, station_task

from .imaging import (
    compare_masters,
    flat_analysis,
    frame_stats,
    leak_self_test,
    qa_set,
    read_data,
    render_array,
    render_dust_map,
)
from .models import BuiltMaster, CalibrationQA, QAVerdict

log = logging.getLogger("substation.calibration")

MASTER_TYPE: dict[str, str] = {
    FrameType.DARK: FrameType.MASTER_DARK,
    FrameType.FLAT: FrameType.MASTER_FLAT,
    FrameType.BIAS: FrameType.MASTER_BIAS,
    FrameType.DARK_FLAT: FrameType.MASTER_DARK_FLAT,
}
TYPE_WORD: dict[str, str] = {
    FrameType.DARK: "dark",
    FrameType.FLAT: "flat",
    FrameType.BIAS: "bias",
    FrameType.DARK_FLAT: "dark flat",
}


def _safe(text: str) -> str:
    """A path part Siril's command line accepts: it splits arguments on spaces, and a dot would be taken for
    the start of an extension (3.125e-05 s → "master_bias_3.fit")."""
    return re.sub(r"[^A-Za-z0-9+-]+", "_", text.replace("α", "a").replace("β", "b")).strip("_") or "x"


def _path(frame: Frame) -> Path | None:
    for c in Copy.objects.filter(frame=frame, present=True).select_related("library"):
        p = Path(c.library.mount_path) / c.rel_path
        if p.is_file():
            return p
    return None


@station_task(queue_name="process", priority=PRIORITY_BULK - 5, max_attempts=2)
def qa_calibration_set(set_id: int) -> dict:
    cs = CalibrationSet.objects.get(pk=set_id)
    frames = list(
        Frame.objects.filter(calibration_set=cs, status=FrameStatus.CATALOGUED).order_by("date_obs_utc")
    )
    stats = {}
    self_test: bool | None = None
    thumbs = Path(settings.PREVIEWS_DIR) / "calibration" / f"set{cs.pk}"
    for i, f in enumerate(frames):
        p = _path(f)
        if p is None:
            continue
        try:
            a = read_data(p, f.integration_index or 0)
        except Exception as exc:  # noqa: BLE001 (an unreadable frame is a QA finding, not a crash)
            CalibrationQA.objects.update_or_create(
                frame=f,
                defaults={
                    "verdict": QAVerdict.REJECT,
                    "reason": f"Couldn't read the image data: {exc}",
                    "stats": {},
                },
            )
            continue
        dark = cs.type in (FrameType.DARK, FrameType.BIAS, FrameType.DARK_FLAT)
        stats[f.sha256] = frame_stats(a, dark=dark)
        if dark and i == 0:
            self_test = leak_self_test(a)
        thumb = thumbs / f"{f.sha256[:20]}.jpg"
        try:
            render_array(a, thumb, width=360)
        except Exception:  # noqa: BLE001
            thumb = Path("")
        CalibrationQA.objects.update_or_create(
            frame=f,
            defaults={
                "verdict": QAVerdict.PASS,
                "stats": stats[f.sha256].as_dict(),
                "thumb_path": str(thumb),
            },
        )
        del a
        report_progress(
            (i + 1) / max(1, len(frames)),
            f"checking {TYPE_WORD.get(cs.type, cs.type)} {i + 1} of {len(frames)}",
        )
    verdicts = qa_set(cs.type, stats)
    if self_test is False:  # the leak check couldn't find synthetic 15 ADU stars on this camera's darks
        verdicts = {k: (v, f"{r} Leak check inconclusive (too noisy).") for k, (v, r) in verdicts.items()}
    for sha, (verdict, reason) in verdicts.items():
        CalibrationQA.objects.filter(frame_id=sha).update(verdict=verdict, reason=reason)
    emit("calibration.updated", {"set_id": cs.pk})
    return {
        "frames": len(frames),
        "rejected": sum(1 for v in verdicts.values() if v[0] == "reject"),
        "leak_self_test": self_test,
    }


def _effective_qa(f: Frame) -> str:
    qa = CalibrationQA.objects.filter(frame=f).first()
    if qa is None:
        return "pass"
    return qa.override or qa.verdict


def flat_calibrator(cs: CalibrationSet) -> Frame | None:
    """For a flat set: a master dark flat at its exposure (same camera and gain), else a master dark at exactly
    that exposure (the same thing by another name), else a master bias; the nearest in time wins."""
    # only masters with a file on disk: a catalogued master whose every copy has gone would fail the build
    # (the 15 Aug RGB flats, 2026-10-12)
    base = Frame.objects.filter(status=FrameStatus.CATALOGUED, copies__present=True).distinct()
    if cs.camera:
        base = base.filter(camera=cs.camera)
    if cs.gain is not None:
        base = base.filter(gain=cs.gain)
    if (
        cs.offset is not None
    ):  # offset shifts the whole bias level: a bias at another offset is the wrong bias
        base = base.filter(offset=cs.offset)

    def nearest(qs):  # noqa: ANN001, ANN202
        found = [f for f in qs if f.date_obs_utc is not None] or list(qs)
        return (
            min(
                found,
                key=lambda f: (
                    abs((f.date_obs_utc - cs.session_start_utc).total_seconds()) if f.date_obs_utc else 0
                ),
            )
            if found
            else None
        )

    for kind in (FrameType.MASTER_DARK_FLAT, FrameType.MASTER_DARK):
        got = nearest(
            base.filter(
                frame_type=kind, exptime_s__gte=cs.exptime_s * 0.999, exptime_s__lte=cs.exptime_s * 1.001
            )
        )
        if got is not None:
            return got
    return nearest(base.filter(frame_type=FrameType.MASTER_BIAS))


def request_build(cs: CalibrationSet, force: bool = False, priority: int = PRIORITY_BULK) -> BuiltMaster:
    bm = BuiltMaster.objects.create(calibration_set=cs, state="queued", method="", report={"force": force})
    enqueue(build_master, bm.pk, priority=priority)
    return bm


def built_library() -> Library:
    root = Path(settings.MASTERS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    lib, _ = Library.objects.get_or_create(
        name="built-masters", defaults={"mount_path": str(root), "enabled": False}
    )
    return lib


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


FLAT_MIN_ADU = 200  # a flat whose light is less than this above its bias or dark flat corrects nothing


def dark_flat_reason(signal: float) -> str:
    return f"Not used: almost dark ({signal:.0f} ADU above bias). Good flats sit at 30–60% of full scale."


def _register(bm: BuiltMaster, cs: CalibrationSet, out: Path) -> Frame:
    """Catalogue the new master so matching can use it. Its values come from the set (inferred, with source)."""
    from apps.ingest.resolve import resolve_frame

    lib = built_library()
    digest = _sha256(out)
    now = timezone.now()
    st = out.stat()
    with transaction.atomic():
        frame, _ = Frame.objects.get_or_create(
            sha256=digest,
            defaults={
                "size_bytes": st.st_size,
                "format": "fits",
                "first_seen_at": now,
                "status": FrameStatus.CATALOGUED,
                "catalogued_at": now,
                "image_count": 1,
            },
        )
        Copy.objects.update_or_create(
            library=lib,
            rel_path=str(out.relative_to(lib.mount_path)),
            defaults={
                "frame": frame,
                "st_dev": st.st_dev,
                "st_ino": st.st_ino,
                "st_size": st.st_size,
                "st_mtime_ns": st.st_mtime_ns,
                "first_seen_at": now,
                "last_seen_at": now,
                "present": True,
            },
        )
        detail = f"built by SubStation from calibration set #{cs.pk}"
        temp = cs.set_temp_c
        if temp is None:
            # no set point recorded (NINA leaves SET-TEMP out at times), but every frame says what the sensor was:
            # use their median, rounded, so a −20 °C dark matches −20 °C lights (M 81 L, 13 Feb, 2026-10-13)
            import statistics

            temps = [
                t
                for t in Frame.objects.filter(calibration_set=cs).values_list("ccd_temp_c", flat=True)
                if t is not None
            ]
            if temps:
                temp = round(statistics.median(temps))
                detail += f"; temperature {temp} °C from its frames' sensor readings"
        values = {
            "frame_type": str(MASTER_TYPE[cs.type]).replace("_", " ").title(),
            "exptime": cs.exptime_s,
            "gain": cs.gain,
            "offset": cs.offset,
            "xbin": cs.xbin,
            "ybin": cs.ybin,
            "camera": cs.camera or None,
            "set_temp": temp,
            "filter": cs.filter_norm if cs.type == FrameType.FLAT else None,
            "date_obs": cs.session_start_utc.isoformat(),
            "telescope": Frame.objects.filter(calibration_set=cs)
            .exclude(telescope=None)
            .values_list("telescope", flat=True)
            .first(),
        }
        frame.metadata.filter(source=MetadataSource.INFERRED).delete()
        MetadataValue.objects.bulk_create(
            [
                MetadataValue(
                    frame=frame,
                    field=k,
                    value=str(v),
                    raw=str(v),
                    source=MetadataSource.INFERRED,
                    source_detail=detail,
                )
                for k, v in values.items()
                if v not in (None, "")
            ]
        )
        resolve_frame(frame, has_integration=False)
        record_geometry(frame, out)
    return frame


def record_geometry(frame: Frame, path: Path) -> None:
    """Keep a built master's size (width:height[:planes]) as a header snapshot, as ingest does for captures, so
    matching can refuse a master of another size (an A7 III writes 6024×4024 or 6000×4000 by session)."""
    from astropy.io import fits

    from apps.catalogue.models import HeaderSnapshot

    h = fits.getheader(path)
    dims = [str(h.get(f"NAXIS{i}")) for i in range(1, (h.get("NAXIS") or 0) + 1)]
    HeaderSnapshot.objects.update_or_create(
        frame=frame,
        image_index=0,
        defaults={"geometry": ":".join(dims), "sample_format": f"BITPIX={h.get('BITPIX')}"},
    )


def backfill_geometry() -> int:
    """Record the size of built masters registered before sizes were kept."""
    from .tasks import source_path

    n = 0
    for bm in BuiltMaster.objects.filter(state="done").exclude(frame=None).select_related("frame"):
        f = bm.frame
        if f is None or f.headers.exists():
            continue
        src = source_path(f)
        if src is not None:
            record_geometry(f, src)
            n += 1
    return n


def previous_master(cs: CalibrationSet, exclude: Path | None = None) -> Frame | None:
    """The latest other master of the same kind (camera, gain, exposure; filter for flats) before this set."""
    from .tasks import source_path

    qs = Frame.objects.filter(
        status=FrameStatus.CATALOGUED,
        frame_type=MASTER_TYPE[cs.type],
        exptime_s__gte=cs.exptime_s * 0.999,
        exptime_s__lte=cs.exptime_s * 1.001,
    )
    if cs.camera:
        qs = qs.filter(camera=cs.camera)
    if cs.gain is not None:
        qs = qs.filter(gain=cs.gain)
    if cs.type == FrameType.FLAT:
        qs = qs.filter(filter_norm=cs.filter_norm)
    for f in qs.exclude(date_obs_utc__gt=cs.session_start_utc).order_by("-date_obs_utc"):
        p = source_path(f)
        if p is not None and (exclude is None or p.resolve() != exclude.resolve()):
            return f
    return None


def _compare(new, previous: Frame, flat: bool, out: Path) -> dict:  # noqa: ANN001
    from .tasks import master_fits, source_path

    try:
        p = source_path(previous)
        old = read_data(master_fits(previous) if p is None or p.suffix.lower() == ".xisf" else p)
        got = compare_masters(new, old, flat)
    except Exception as exc:  # noqa: BLE001 (a comparison never fails the build)
        return {"against": previous.sha256, "error": str(exc)}
    if got is None:
        return {"against": previous.sha256, "error": "The two masters are different sizes."}
    summary, img = got
    render_array(img, out)
    name = Copy.objects.filter(frame=previous, present=True).values_list("rel_path", flat=True).first() or ""
    return {
        "against": previous.sha256,
        "against_file": Path(name).name,
        "against_date": previous.date_obs_utc.isoformat() if previous.date_obs_utc else None,
        **summary,
    }


def one_row_order(work: Path, prefix: str) -> int:
    """Put every converted frame in the first one's row order. Siril writes XISF bottom-up and keeps NINA's FITS
    top-down, so a set mixing the two (or the same flats saved in both formats) would stack each frame with an
    upside-down twin: a mirrored master with every dust mote twice. Returns how many were flipped."""
    import numpy as np
    from astropy.io import fits

    from .tasks import _top_down

    files = sorted(work.glob(f"{prefix}[0-9]*.fit"))
    if not files:
        return 0
    want = _top_down(files[0])
    n = 0
    for p in files[1:]:
        if _top_down(p) == want:
            continue
        with fits.open(p, memmap=False) as hl:
            hdu = hl[0]
            data = np.flip(hdu.data, axis=-2)
            header = hdu.header.copy()
        header["ROWORDER"] = ("TOP-DOWN" if want else "BOTTOM-UP", "flipped by SubStation to match the set")
        fits.PrimaryHDU(data=data, header=header).writeto(p, overwrite=True)
        n += 1
    return n


@station_task(queue_name="stack", slot="siril_heavy", max_attempts=1)
def build_master(built_id: int) -> dict:

    bm = BuiltMaster.objects.select_related("calibration_set").get(pk=built_id)
    cs = bm.calibration_set
    BuiltMaster.objects.filter(pk=bm.pk).update(state="running", error=None)
    frames = list(
        Frame.objects.filter(calibration_set=cs, status=FrameStatus.CATALOGUED).order_by("date_obs_utc")
    )
    if not CalibrationQA.objects.filter(frame__in=frames).exists():
        qa_calibration_set.call(cs.pk)
    use, excluded = [], []
    for f in frames:
        v = _effective_qa(f)
        qa = CalibrationQA.objects.filter(frame=f).first()
        if v == "reject":
            excluded.append({"sha256": f.sha256, "reason": qa.reason if qa else "rejected"})
        else:
            p = _path(f)
            if p is None:
                excluded.append({"sha256": f.sha256, "reason": "no copy on disk"})
            else:
                use.append((f, p))
    word = TYPE_WORD.get(cs.type, cs.type)
    from .tasks import is_processed_rgb

    rgb = bool(use) and is_processed_rgb(use[0][0])
    if rgb and cs.type != FrameType.FLAT:
        BuiltMaster.objects.filter(pk=bm.pk).update(
            state="blocked",
            frames_excluded=excluded,
            finished_at=timezone.now(),
            reason=(f"8-bit colour {word} frames, not raw. Can't calibrate raw subs."),
        )
        return {"result": "processed rgb"}
    if len(use) < 3:
        BuiltMaster.objects.filter(pk=bm.pk).update(
            state="failed",
            reason=f"Only {len(use)} usable {word} frames; needs 3.",
            frames_excluded=excluded,
            finished_at=timezone.now(),
        )
        return {"result": "too few"}
    # 8-bit colour flats (the camera already took off its black level) calibrate 8-bit colour lights only, by
    # division; a raw bias or dark flat doesn't apply to them
    calibrator = flat_calibrator(cs) if cs.type == FrameType.FLAT and not rgb else None
    if cs.type == FrameType.FLAT and calibrator is None and not rgb and not bm.report.get("force"):
        BuiltMaster.objects.filter(pk=bm.pk).update(
            state="blocked",
            frames_excluded=excluded,
            finished_at=timezone.now(),
            reason=(
                f"No master dark flat at {cs.exptime_s:g} s or master bias for this camera. "
                "Build one first, or build anyway."
            ),
        )
        return {"result": "blocked"}
    work = Path(settings.WORK_DIR) / "masters-build" / f"set{cs.pk}_{bm.pk}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    from apps.engine.siril import heavy_memory

    _heavy = heavy_memory()
    try:
        eng = _heavy.__enter__()
        report_progress(0.05, f"preparing {len(use)} {word} frames")
        for i, (_f, p) in enumerate(use, start=1):
            os.symlink(p, work / f"in_{i:05d}{p.suffix.lower()}")
        cal = None
        if calibrator is not None:
            from .tasks import master_fits

            cal = master_fits(calibrator)  # before `cd`: converting a master changes Siril's directory
        eng.run(f"cd {work}")
        eng.run("convert raw -out=.", timeout=3600)  # any format → FITS sequence raw_00001.fit …
        flipped = one_row_order(work, "raw_")
        out_dir = Path(settings.MASTERS_DIR) / _safe(cs.camera or "camera") / _safe(word)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = _safe(
            f"master_{word}_{cs.filter_norm or ''}_{f'{cs.exptime_s:g}'.replace('.', 'p')}s_set{cs.pk}_b{bm.pk}"
        ).replace("__", "_")
        out = out_dir / name
        colour = False
        from .tasks import is_colour_frame

        colour = is_colour_frame(use[0][0]) and not rgb  # a CFA mosaic, not already-colour planes
        report_progress(0.3, "stacking")
        if cs.type == FrameType.FLAT:
            seq = "raw_"
            method = "flats"
            if calibrator is not None:
                from .tasks import _top_down, oriented_master

                first = work / "raw_00001.fit"  # the dark flat in the flats' row order (see oriented_master)
                if first.exists() and cal is not None:
                    cal = oriented_master(Path(cal), _top_down(first))
                flag = "-bias" if calibrator.frame_type == FrameType.MASTER_BIAS else "-dark"
                cfa = " -cfa -equalize_cfa" if colour else ""
                eng.run(f"calibrate raw_ {flag}={cal}{cfa} -prefix=pp_", timeout=3600)
                seq = "pp_raw_"
                method = f"flats calibrated by the master {'bias' if flag == '-bias' else 'dark flat'}"
            from apps.engine.siril import EngineError

            try:
                eng.run(f"stack {seq} rej w 3 3 -norm=mul -out={out} -32b", timeout=3600)
            except EngineError as e:
                # blank frames (a closed cap, an 8-bit exposure of nothing) have no spread to normalise: Siril
                # stops with "MAD is null"; say what that means rather than pass on Siril's words (set 2, 2026-10-12)
                if not any("MAD is null" in line for line in e.log):
                    raise
                BuiltMaster.objects.filter(pk=bm.pk).update(
                    state="blocked",
                    frames_used=0,
                    frames_excluded=excluded,
                    finished_at=timezone.now(),
                    error="",
                    reason="Not used: the frames are blank (no signal to normalise). Good flats sit at 30–60% "
                    "of full scale.",
                )
                shutil.rmtree(work, ignore_errors=True)
                return {"result": "blank"}
            method += ", winsorised σ 3/3, multiplicative normalisation"
            if rgb:
                method += (
                    "; 8-bit colour: for 8-bit colour lights only (approximate, as that data isn't linear)"
                )
        else:
            eng.run(f"stack raw_ rej w 3 3 -nonorm -out={out} -32b", timeout=3600)
            method = "winsorised σ 3/3, no normalisation"
        result = out_dir / f"{name}.fit"
        report_progress(0.8, "analysing the master")
        a = read_data(result)
        if a.ndim == 3:  # colour planes: analyse their mean
            a = a.mean(axis=0)
        report: dict = {"stats": frame_stats(a).as_dict()}
        if flipped:  # frames in another row order, turned to match before stacking (see one_row_order)
            report["flipped"] = flipped
        motes = None
        dust_map = None
        note = ""
        if cs.type == FrameType.FLAT:
            flat, dust_map = flat_analysis(a, cfa=colour)
            report |= flat
            motes = report.get("dust_motes")
            if "falloff" not in report:
                note = (
                    "Too faint to analyse: after calibration the flat's level is at or below zero, so there's no "
                    "illumination to measure. Flats should sit at 30–60% of full scale."
                )
        prev = result.with_suffix(".jpg")
        render_array(a, prev, motes=None, thumb=result.with_name(result.stem + "_t.jpg"))
        if cs.type == FrameType.FLAT and dust_map is not None:
            render_dust_map(dust_map, motes or [], a.shape[0], result.with_name(result.stem + "_motes.jpg"))
        previous = previous_master(cs, exclude=result)
        if previous is not None:
            report["comparison"] = _compare(
                a, previous, cs.type == FrameType.FLAT, result.with_name(result.stem + "_cmp.jpg")
            )
        signal = float(np.median(a)) if cs.type == FrameType.FLAT else None  # read_data gives ADU
        del a
        if signal is not None and signal < (1 if rgb else FLAT_MIN_ADU):
            # near-dark "flats" (a test exposure filed as a flat, a closed cap) would wreck every light they touch
            BuiltMaster.objects.filter(pk=bm.pk).update(
                state="blocked",
                method=method,
                calibrated_with=calibrator,
                frames_used=len(use),
                frames_excluded=excluded,
                output_path=str(result),
                preview_path=str(prev),
                report=report,
                engine_version=eng.version,
                finished_at=timezone.now(),
                reason=dark_flat_reason(signal),
            )
            emit("calibration.updated", {"set_id": cs.pk})
            return {"result": "blocked"}
        frame = _register(bm, cs, result)
        # a rebuild replaces the set's earlier master in matching; its file stays for comparison and provenance
        old = (
            BuiltMaster.objects.filter(calibration_set=cs, state="done")
            .exclude(pk=bm.pk)
            .exclude(frame=None)
            .exclude(frame=frame)
            .values_list("frame_id", flat=True)
        )
        Frame.objects.filter(pk__in=list(old)).update(status=FrameStatus.IGNORED)
        BuiltMaster.objects.filter(pk=bm.pk).update(
            state="done",
            frame=frame,
            method=method,
            calibrated_with=calibrator,
            frames_used=len(use),
            frames_excluded=excluded,
            output_path=str(result),
            preview_path=str(prev),
            report=report,
            engine_version=eng.version,
            finished_at=timezone.now(),
            reason=note,
        )
    except Exception as exc:
        BuiltMaster.objects.filter(pk=bm.pk).update(
            state="failed", error=str(exc), finished_at=timezone.now()
        )
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
        _heavy.__exit__(None, None, None)
    emit("calibration.updated", {"set_id": cs.pk})
    _apply_chosen(cs)
    return {"frames": len(use), "excluded": len(excluded)}


def _apply_chosen(cs: CalibrationSet) -> int:
    """Sessions that chose this flat set before its master existed (Change → flat set) now use it."""
    from .models import CalibrationMatch, MatchState
    from .tasks import queue_measure

    bm = (
        BuiltMaster.objects.filter(calibration_set=cs, state="done")
        .exclude(frame=None)
        .order_by("-pk")
        .first()
    )
    if bm is None:
        return 0
    n = 0
    for cm in CalibrationMatch.objects.filter(pending_flat_set=cs).select_related("frame"):
        cm.flat_id, cm.pending_flat_set, cm.pinned = bm.frame_id, None, True
        cm.flat_note, cm.reason = "Chosen by you", ""
        ok = cm.dark_id is not None or "8-bit colour" in (cm.dark_note or "")
        if not ok:
            from .tasks import is_processed_rgb

            ok = is_processed_rgb(cm.frame)
            if ok:
                cm.dark_note = "No dark: 8-bit colour image"
        cm.state = MatchState.MATCHED if ok else MatchState.AWAITING
        cm.save()
        if ok:
            queue_measure(cm.frame, force=True)
        n += 1
    return n


@station_task(queue_name="process", max_attempts=1)
def reanalyse_built(built_id: int) -> dict:
    """Run the master's analysis again (after the analysis improves) without rebuilding it."""
    from .tasks import is_colour_frame

    bm = BuiltMaster.objects.select_related("calibration_set").get(pk=built_id)
    if bm.state != "done" or not bm.output_path or not Path(bm.output_path).is_file():
        return {"result": "nothing to analyse"}
    cs = bm.calibration_set
    result = Path(bm.output_path)
    a = read_data(result)
    report = {k: v for k, v in (bm.report or {}).items() if k in ("comparison", "force")}
    report["stats"] = frame_stats(a).as_dict()
    note = ""
    if cs.type == FrameType.FLAT:
        first = Frame.objects.filter(calibration_set=cs).first()
        flat, dust_map = flat_analysis(a, cfa=bool(first and is_colour_frame(first)))
        report |= flat
        if "falloff" not in report:
            note = (
                "Too faint to analyse: after calibration the flat's level is at or below zero, so there's no "
                "illumination to measure. Flats should sit at 30–60% of full scale."
            )
        motes_jpg = result.with_name(result.stem + "_motes.jpg")
        motes_jpg.unlink(missing_ok=True)
        if dust_map is not None:
            render_dust_map(dust_map, report.get("dust_motes", []), a.shape[0], motes_jpg)
    BuiltMaster.objects.filter(pk=bm.pk).update(report=report, reason=note)
    emit("calibration.updated", {"set_id": cs.pk})
    return {"motes": report.get("dust_mote_count")}
