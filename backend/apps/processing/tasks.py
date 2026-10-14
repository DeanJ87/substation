"""Processing tasks: match (cheap), calibrate and measure one sub (Siril), grade its session."""

from __future__ import annotations

import logging
import math
import os
import shutil
import time
import uuid
from pathlib import Path

import numpy as np
from django.conf import settings
from django.utils import timezone

from apps.catalogue.models import MASTER_TYPES, Copy, Frame, FrameStatus, FrameType
from substation.events.emit import emit
from substation.tasks import PRIORITY_BULK, PRIORITY_LIVE, enqueue, report_progress, station_task

from .grading import grade_session
from .matching import update_match
from .models import CalibrationMatch, MatchState, MeasureState, SubMeasurement

log = logging.getLogger("substation.processing")
LIVE_AGE_S = 30 * 60


def work_dir(*parts: str) -> Path:
    p = Path(settings.WORK_DIR).joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def source_path(frame: Frame) -> Path | None:
    for c in Copy.objects.filter(frame=frame, present=True).select_related("library"):
        p = Path(c.library.mount_path) / c.rel_path
        if p.is_file():
            return p
    return None


def priority_for(frame: Frame) -> int:
    """New subs first (tonight's session graded as it arrives), unless Settings → Workers says in order."""
    from .config import processing_settings

    if processing_settings().get("queue", {}).get("priority_mode") == "in_order":
        return PRIORITY_BULK - 2
    age = (timezone.now() - frame.first_seen_at).total_seconds()
    return PRIORITY_LIVE - 2 if age < LIVE_AGE_S else PRIORITY_BULK - 2


def after_resolve(frame: Frame) -> None:
    """Called after a frame is (re)resolved: lights are matched and queued for calibration; a master that
    changed re-matches every light (spec 002)."""
    if not getattr(settings, "PROCESSING_ENABLED", True):
        return
    if frame.frame_type in MASTER_TYPES:
        enqueue(rematch_lights, dedupe_key="rematch-lights", priority=PRIORITY_LIVE - 1, fresh=True)
        return
    if frame.frame_type == FrameType.LIGHT:
        cm = update_match(frame)
        if cm is not None and cm.state == MatchState.MATCHED:
            queue_measure(frame)


def queue_measure(frame: Frame, force: bool = False) -> None:
    """Queue calibration and measurement; `force` redoes a finished one (newer calibration accepted)."""
    m = SubMeasurement.objects.filter(frame=frame).first()
    if m is not None and m.state == MeasureState.DONE and not force:
        return
    SubMeasurement.objects.update_or_create(frame=frame, defaults={"state": MeasureState.QUEUED})
    enqueue(
        calibrate_measure, frame.sha256, dedupe_key=f"measure:{frame.sha256}", priority=priority_for(frame)
    )


def _retry_locked(fn, tries: int = 4):  # noqa: ANN001, ANN202
    """A long pass over every light shouldn't fail on one busy moment of the database."""
    from django.db import OperationalError

    for i in range(tries):
        try:
            return fn()
        except OperationalError as exc:
            if "locked" not in str(exc) or i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    return None


def _same_night_flat_arrived(f: Frame, done: SubMeasurement, cm) -> bool:  # noqa: ANN001
    """The sub's match now names a flat from its own night, and it was calibrated with a different one."""
    if cm.pinned or not cm.flat_id or cm.flat_id == done.flat_id or cm.dark_id != done.dark_id:
        return False
    flat = Frame.objects.filter(pk=cm.flat_id).select_related("night").first()
    return bool(flat and flat.night and f.night and flat.night.date == f.night.date)


@station_task(queue_name="process", max_attempts=2)
def rematch_lights() -> dict:
    _wait_for_earlier_rematch()
    cache: dict = {}
    lights = Frame.objects.filter(frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED).select_related(
        "night"
    )
    n = queued = 0
    # ids first, then fresh chunks: a long-open cursor would hold one snapshot for the whole run
    ids = list(lights.values_list("pk", flat=True))
    for f in (f for i in range(0, len(ids), 200) for f in lights.filter(pk__in=ids[i : i + 200])):
        cm = _retry_locked(lambda f=f: update_match(f, cache))
        n += 1
        if cm is None or cm.state != MatchState.MATCHED or not getattr(settings, "PROCESSING_ENABLED", True):
            continue
        done = SubMeasurement.objects.filter(frame=f, state=MeasureState.DONE).first()
        if done is None:
            queue_measure(f)
            queued += 1
        elif _same_night_flat_arrived(f, done, cm):
            # calibrated while its own night's flats were still being built: redo it with them (the race the
            # owner hit on 2026-10-11); other newer-calibration cases wait for the owner (002 C11)
            queue_measure(f, force=True)
            queued += 1
    from apps.catalogue.models import Dataset
    from apps.ingest.tasks.reresolve import tidy_datasets

    from .effective import recount_grades

    tidy = tidy_datasets()  # 006-DR-34: stale or emptied datasets, whatever moved their subs
    for ds in Dataset.objects.all():
        recount_grades(ds)
    emit("dataset.updated", {"dataset_id": None})
    return {"lights": n, "queued": queued, **tidy}


def _wait_for_earlier_rematch() -> None:
    """One re-match at a time (002-DR-25): a later run waits for one already going, which may have read the masters
    before the newest; running together, three re-matches of every light slowed each other (2026-10-14)."""
    from django.db.models import Q

    from substation.tasks import Reschedule, current_task_id
    from substation.tasks.models import Task, TaskStatus

    task_id = current_task_id.get()
    me = Task.objects.filter(pk=task_id).values("pk", "started_at").first() if task_id else None
    if me is None:
        return
    earlier = (
        Task.objects.filter(name__endswith=".rematch_lights", status=TaskStatus.RUNNING)
        .exclude(pk=me["pk"])
        .filter(Q(started_at__lt=me["started_at"]) | Q(started_at=me["started_at"], pk__lt=me["pk"]))
    )
    if earlier.exists():
        raise Reschedule(60, "Waiting for the re-match already running.")


def _save_stars(calibrated: Path, stars: list, out: Path) -> None:
    """Keep the detected stars (positions in 0–1 of the frame; Siril's y already runs top-down as the preview is
    drawn, checked against star brightness on a real sub; FWHM and roundness) for the Stars and FWHM map views (003 G15). The brightest 3,000 are plenty to see a pattern."""
    import json

    from astropy.io import fits

    try:
        h = fits.getheader(calibrated)
        w, ht = int(h.get("NAXIS1") or 0), int(h.get("NAXIS2") or 0)
        if not (w and ht and stars):
            return
        keep = sorted(stars, key=lambda st: -st.amplitude)[:3000]
        rows = [
            [
                round(st.x / w, 5),
                round(st.y / ht, 5),
                round((st.fwhm_x + st.fwhm_y) / 2, 2),
                round(min(st.fwhm_x, st.fwhm_y) / max(st.fwhm_x, st.fwhm_y), 3)
                if max(st.fwhm_x, st.fwhm_y)
                else 1,
            ]
            for st in keep
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"width": w, "height": ht, "stars": rows}))
    except Exception as exc:  # noqa: BLE001 (a missing overlay must never fail a measurement)
        log.warning("Couldn't keep the star list: %s", exc)


@station_task(queue_name="process", priority=PRIORITY_BULK - 10, max_attempts=2)
def rerender_previews(dataset_id: int | None = None, colour_only: bool = True) -> dict:
    """Redraw sub previews (after the preview rules change): from the calibrated file when it is still cached,
    else from the capture itself. `colour_only` redraws only grey previews of colour data, which is what one-shot
    colour subs measured before colour previews looked like."""
    from astropy.io import fits
    from PIL import Image

    from .previews import render

    def grey_colour(prev: Path, src: Path) -> bool:
        try:
            if Image.open(prev).mode != "L":
                return False
            h = fits.getheader(src)
        except (OSError, ValueError):
            return False
        return bool(h.get("BAYERPAT")) or h.get("NAXIS3") == 3

    qs = (
        SubMeasurement.objects.filter(state=MeasureState.DONE)
        .exclude(preview_path="")
        .select_related("frame")
    )
    if dataset_id is not None:
        qs = qs.filter(frame__dataset_id=dataset_id)
    ids = list(qs.values_list("pk", flat=True))
    done = 0
    for i in range(0, len(ids), 100):
        for m in SubMeasurement.objects.filter(pk__in=ids[i : i + 100]).select_related("frame"):
            cal = Path(m.calibrated_path) if m.calibrated_path else None
            src, raw = (cal, False) if cal and cal.exists() else (source_path(m.frame), True)
            if src is None:
                continue
            out = Path(m.preview_path)
            if colour_only and not grey_colour(out, src):
                continue
            try:
                render(src, out, out.with_name(out.stem + "_t.jpg"), raw=raw)
                done += 1
            except Exception as exc:  # noqa: BLE001 (one bad file must not stop the rest)
                log.warning("Preview redraw failed for %s: %s", m.frame_id[:12], exc)
        report_progress(min(1.0, (i + 100) / max(1, len(ids))), f"redrawing {len(ids)} previews")
    return {"previews": done, "of": len(ids)}


def master_fits(master: Frame) -> Path:
    """A master's integration image as FITS (Siril calibrates from FITS only), converted once and cached."""
    from apps.engine.siril import engine

    out = work_dir("masters") / f"{master.sha256[:20]}.fit"
    if out.exists():
        return out
    src = source_path(master)
    if src is None:
        raise RuntimeError(f"No copy of the master {master.sha256[:12]} is on disk.")
    # Several workers may need the same master at once: each converts in its own folder, then the finished file
    # is moved into place atomically, so nobody ever reads a half-written master.
    tmp = work_dir("tmp", f"m{master.sha256[:12]}_{uuid.uuid4().hex[:12]}")  # PIDs repeat across containers
    link = tmp / f"master{src.suffix.lower()}"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(src, link)
    eng = engine()
    eng.run(f"cd {tmp}")
    eng.run(f"load {link.name}")
    eng.run("save master_fits")
    if not out.exists():
        os.replace(tmp / "master_fits.fit", out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _top_down(fits_path: Path) -> bool:
    """Whether a FITS file stores its top row first. Siril keeps a NINA FITS light as written (ROWORDER
    TOP-DOWN) but writes converted XISF masters bottom-up, so the two can disagree."""
    from astropy.io import fits

    return str(fits.getheader(fits_path).get("ROWORDER", "")).strip().upper() == "TOP-DOWN"


def oriented_master(master_path: Path, top_down: bool) -> Path:
    """The master in the light's row order. A flat or dark applied upside down puts the OAG shadow, dust motes
    and amp glow on the wrong side (M81 Hα, Feb 2026: NINA FITS lights with a WBPP XISF flat, owner 2026-10-12).
    Flipped copies are cached beside the converted master."""
    if _top_down(master_path) == top_down:
        return master_path
    from astropy.io import fits

    out = master_path.with_name(f"{master_path.stem}_{'td' if top_down else 'bu'}.fit")
    # a cached copy is only trusted when it's the same size as its source: the same pixels, flipped
    if out.exists() and out.stat().st_size == master_path.stat().st_size:
        return out
    with fits.open(master_path, memmap=False) as hl:
        hdu = next(h for h in hl if h.data is not None)
        data = np.flip(hdu.data, axis=-2)  # rows; colour planes (3, h, w) keep their order
        header = hdu.header.copy()
    header["ROWORDER"] = ("TOP-DOWN" if top_down else "BOTTOM-UP", "flipped by SubStation to match the light")
    # workers in different containers can share a PID: a unique temporary name, then an atomic rename
    import uuid

    tmp = out.with_suffix(f".tmp{uuid.uuid4().hex}.fit")
    try:
        fits.PrimaryHDU(data=data, header=header).writeto(tmp, overwrite=True)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def is_colour_frame(frame: Frame) -> bool:
    from apps.ingest.fields import is_colour
    from apps.ingest.tasks.reresolve import header_from_snapshot

    img = header_from_snapshot(frame)
    return bool(img and is_colour(img))


def planes(frame: Frame) -> int:
    """Image planes from the header snapshot's geometry ("6000:4000:3" is 3): 3 means already colour (RGB)."""
    snap = frame.headers.filter(image_index=frame.integration_index or 0).first() or frame.headers.first()
    parts = (snap.geometry if snap else "").split(":")
    return int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1


def is_processed_rgb(frame: Frame) -> bool:
    """8-bit colour: the camera saved processed (JPEG-like) data rather than raw, so raw masters can't apply."""
    if planes(frame) != 3:
        return False
    snap = frame.headers.filter(image_index=frame.integration_index or 0).first() or frame.headers.first()
    fmt = (snap.sample_format if snap else "").replace(" ", "").upper()
    return fmt in ("BITPIX=8", "UINT8")


def _header(frame: Frame, key: str) -> float | None:
    snap = frame.headers.filter(image_index=frame.integration_index or 0).first() or frame.headers.first()
    if snap is None:
        return None
    v = (snap.keywords or {}).get(key, {}).get("value")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pixel_scale(frame: Frame) -> float | None:
    pix, focal = _header(frame, "XPIXSZ"), _header(frame, "FOCALLEN")
    if not pix or not focal:
        return None
    return 206.265 * pix * (frame.xbin or 1) / focal


def calibrate_file(frame: Frame, cm: CalibrationMatch, src: Path, tmp: Path, dest: Path) -> None:
    """Calibrate one sub with its matched masters into `dest` (debayered if colour). Changes Siril's directory."""
    from apps.engine.siril import engine

    dark = master_fits(cm.dark) if cm.dark else None
    flat = master_fits(cm.flat) if cm.flat else None
    colour = is_colour_frame(frame)
    eng = engine()
    link = tmp / f"light{src.suffix.lower()}"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(src, link)
    eng.run(f"cd {tmp}")
    eng.run(f"load {link.name}")
    eng.run("save light_in")
    # masters in the light's row order (see oriented_master)
    td = _top_down(tmp / "light_in.fit")
    dark = oriented_master(dark, td) if dark else None
    flat = oriented_master(flat, td) if flat else None
    rgb = planes(frame) == 3  # already colour: nothing to debayer
    if dark and flat:
        cfa = " -cfa -equalize_cfa -debayer" if colour and not rgb else ""
        eng.run(
            f"calibrate_single light_in.fit -dark={dark} -flat={flat} -cc=dark{cfa} -prefix=pp_", timeout=600
        )
    elif flat:  # a flat with no dark: 8-bit colour lights, whose black level the camera already removed
        cfa = " -cfa -equalize_cfa -debayer" if colour and not rgb else ""
        eng.run(f"calibrate_single light_in.fit -flat={flat}{cfa} -prefix=pp_", timeout=600)
    elif colour and not rgb:  # calibrated in the camera (Seestar): only debayer (calibrate_single does that)
        # nothing is subtracted or divided, so 16-bit data stays 16-bit: half the size of float, nothing lost
        eng.run("set16bits")
        try:
            eng.run("calibrate_single light_in.fit -cfa -debayer -prefix=pp_", timeout=600)
        finally:
            eng.run("set32bits")
    else:
        eng.run("save pp_light_in")
    produced = tmp / "pp_light_in.fit"
    if not produced.exists():
        raise RuntimeError("Siril wrote no calibrated file.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(produced, dest)
    for p in tmp.glob("light_in*"):
        p.unlink(missing_ok=True)


def calibrate_batch(items: list[tuple[Frame, CalibrationMatch, Path, Path]], tmp: Path) -> list[Frame]:
    """Calibrate many subs at once into their `dest`s: subs sharing their masters (and colour) are converted to one
    sequence and calibrated by one Siril command, which uses every thread, instead of one Siril round trip each
    (135 subs took 12 minutes that way, Siril a quarter busy, 2026-10-13). Returns the frames it couldn't do, for
    calibrate_file one at a time. Changes Siril's directory."""
    from apps.engine.siril import engine

    from .calibration import one_row_order

    groups: dict[tuple, list[tuple[Frame, CalibrationMatch, Path, Path]]] = {}
    for it in items:
        frame, cm = it[0], it[1]
        key = (cm.dark_id, cm.flat_id, is_colour_frame(frame), planes(frame) == 3)
        groups.setdefault(key, []).append(it)
    left: list[Frame] = []
    eng = engine()
    for n, ((_dark, _flat, colour, rgb), group) in enumerate(groups.items()):
        g = tmp / f"batch{n}"
        shutil.rmtree(g, ignore_errors=True)
        g.mkdir(parents=True)
        try:
            for j, (_f, _cm, src, _dest) in enumerate(group, start=1):
                os.symlink(src, g / f"src_{j:05d}{src.suffix.lower()}")
            eng.run(f"cd {g}")
            eng.run("convert light -out=.", timeout=3600)  # any format → light_00001.fit …, in input order
            lights = sorted(g.glob("light_[0-9]*.fit"))
            if len(lights) != len(group):  # a file Siril couldn't read: do this group one at a time
                left += [f for f, *_ in group]
                continue
            one_row_order(g, "light_")  # one row order, so one orientation of each master fits them all
            td = _top_down(lights[0])
            cm = group[0][1]
            dark = oriented_master(master_fits(cm.dark), td) if cm.dark else None
            flat = oriented_master(master_fits(cm.flat), td) if cm.flat else None
            cfa = " -cfa -equalize_cfa -debayer" if colour and not rgb else ""
            prefix = "pp_"
            if dark and flat:
                eng.run(
                    f"calibrate light_ -dark={dark} -flat={flat} -cc=dark{cfa} -prefix=pp_",
                    timeout=7200,
                    quiet=True,
                )
            elif flat:  # 8-bit colour lights: the camera already removed the black level
                eng.run(f"calibrate light_ -flat={flat}{cfa} -prefix=pp_", timeout=7200, quiet=True)
            elif colour and not rgb:  # calibrated in the camera (Seestar): only debayer, kept at 16 bits
                eng.run("set16bits")
                try:
                    eng.run("calibrate light_ -cfa -debayer -prefix=pp_", timeout=7200, quiet=True)
                finally:
                    eng.run("set32bits")
            else:
                prefix = ""  # nothing to apply: the converted files are the result
            for j, (frame, _cm, _src, dest) in enumerate(group, start=1):
                produced = g / f"{prefix}light_{j:05d}.fit"
                if not produced.exists():
                    left.append(frame)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                if (
                    produced.is_symlink()
                ):  # Siril links a FITS it only converts: copy the real file, never the link
                    shutil.copyfile(produced.resolve(), dest)
                else:
                    os.replace(produced, dest)
        except Exception:  # noqa: BLE001 (the group is done one at a time instead)
            log.warning(
                "Batch calibration of %s subs failed; calibrating them one at a time",
                len(group),
                exc_info=True,
            )
            left += [f for f, *_ in group]
        finally:
            shutil.rmtree(g, ignore_errors=True)
    return left


def prune_calibrated(budget_bytes: int | None = None) -> int:
    """Calibrated subs are a cache (a debayered 24 MP sub is ~290 MB): keep the newest within the budget and
    delete the oldest. Integration touches its inputs first and recalibrates any that were pruned."""
    budget = budget_bytes if budget_bytes is not None else int(settings.CALIBRATED_CACHE_GB * 1024**3)
    root = Path(settings.WORK_DIR) / "calibrated"
    if not root.exists():
        return 0
    files = []
    for p in root.rglob("*.fit"):
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        files.append((st.st_mtime, st.st_size, p))
    total = sum(f[1] for f in files)
    removed = 0
    # a stack touches its inputs when it starts and may read them for an hour or more: never take a file used in
    # the last 3 hours, even over budget (a running stack lost its subs to this, 2026-10-13)
    recent = time.time() - 3 * 3600
    for mt, size, p in sorted(files):
        if total <= budget:
            break
        if mt > recent:
            continue
        p.unlink(missing_ok=True)
        total -= size
        removed += 1
    if removed:
        log.info("Pruned %d calibrated subs to keep the cache under %.0f GB", removed, budget / 1024**3)
    return removed


@station_task(queue_name="process", max_attempts=2)
def calibrate_measure(sha256: str) -> dict:
    """Spec 003 US1: calibrate one sub with its matched master dark and flat, then measure it."""
    from apps.engine import parse
    from apps.engine.siril import engine

    from .previews import render

    t0 = time.monotonic()
    frame = Frame.objects.get(pk=sha256)
    cm = CalibrationMatch.objects.filter(frame=frame, state=MatchState.MATCHED).first()
    m, _ = SubMeasurement.objects.get_or_create(frame=frame)
    if cm is None or frame.status != FrameStatus.CATALOGUED:
        return {"result": "not matched"}
    src = source_path(frame)
    if src is None:
        m.state, m.error = MeasureState.FAILED, "No copy of this sub is on disk."
        m.save()
        return {"result": "missing"}
    try:
        report_progress(0.05, "preparing calibration masters")
        out_dir = work_dir("calibrated", f"ds{frame.dataset_id or 0}")
        calibrated = out_dir / f"{sha256[:20]}.fit"
        tmp = work_dir("tmp", sha256[:16])
        eng = engine()
        report_progress(0.2, f"calibrating {src.name}")
        calibrate_file(frame, cm, src, tmp, calibrated)
        report_progress(0.7, "measuring")
        stars_file = tmp / "stars.lst"
        eng.run(f"load {calibrated}")
        found = eng.run(f"findstar -out={stars_file}")
        noise = parse.bgnoise(eng.run("bgnoise").log)
        st = parse.stat(eng.run("stat").log)
        n, fwhm = parse.found_stars(found.log)
        stars = parse.star_list(stars_file)
        rnd = parse.roundness(stars)
        scale = pixel_scale(frame)
        m.dark, m.flat = cm.dark, cm.flat
        m.calibrated_path = str(calibrated)
        m.stars, m.fwhm_px = n, fwhm
        m.fwhm_arcsec = fwhm * scale if fwhm and scale else None
        m.roundness = rnd
        m.eccentricity = math.sqrt(max(0.0, 1 - rnd * rnd)) if rnd else None
        m.background = st[1] if st else None
        m.noise = noise
        m.snr = (st[0] - st[1]) / noise if st and noise else None  # crude; stacks get a proper SNR
        m.pixel_scale = scale
        m.engine_version = eng.version
        report_progress(0.85, "preview")
        prev_dir = Path(settings.PREVIEWS_DIR) / f"ds{frame.dataset_id or 0}"
        _save_stars(calibrated, stars, prev_dir / f"{sha256[:20]}_stars.json")
        make_full_view(
            frame, calibrated
        )  # 100% view and inspector, ready before anyone asks (owner 2026-10-10)
        try:
            night = frame.night.date.isoformat() if frame.night else "unknown"
            render(
                calibrated,
                prev_dir / f"{sha256[:20]}.jpg",
                prev_dir / f"{sha256[:20]}_t.jpg",
                session=prev_dir / "stretch" / f"{night}.json",
            )
            m.preview_path = str(prev_dir / f"{sha256[:20]}.jpg")
        except Exception as exc:  # noqa: BLE001 (a preview must never fail the measurement)
            log.warning("Preview failed for %s: %s", sha256[:12], exc)
        m.state, m.error = MeasureState.DONE, None
        m.seconds = round(time.monotonic() - t0, 2)
        m.measured_at = timezone.now()
        m.save()
        shutil.rmtree(tmp, ignore_errors=True)
        from .solving import available, solve_light

        if available():  # where it really points (spec 009), while the calibrated file is still cached
            enqueue(solve_light, sha256, dedupe_key=f"solve:{sha256}")
        prune_calibrated()
    except Exception as exc:
        m.state, m.error = MeasureState.FAILED, str(exc)
        m.save()
        raise
    if frame.dataset_id:
        grade_session(frame.dataset_id, frame.night_id)
        emit("frame.updated", {"sha256": sha256, "fields": ["grade"]})
        emit("dataset.updated", {"dataset_id": frame.dataset_id})
    return {"stars": m.stars, "fwhm_px": m.fwhm_px, "seconds": m.seconds}


def _star_map_path(frame: Frame) -> Path:
    return Path(settings.PREVIEWS_DIR) / f"ds{frame.dataset_id or 0}" / f"{frame.sha256[:20]}_stars.json"


@station_task(queue_name="process", priority=PRIORITY_BULK - 25, max_attempts=2)
def star_map(sha256: str) -> dict:
    """The Stars and FWHM map for a sub measured before star lists were kept (owner 2026-10-10): from the cached
    calibrated file when there is one (a few seconds), else by measuring the sub again."""
    from apps.engine import parse
    from apps.engine.siril import engine

    frame = Frame.objects.get(pk=sha256)
    out = _star_map_path(frame)
    if out.exists():
        return {"result": "already there"}
    m = SubMeasurement.objects.filter(frame=frame).first()
    cal = Path(m.calibrated_path) if m and m.calibrated_path else None
    if cal is None or not cal.exists():
        enqueue(calibrate_measure, sha256, dedupe_key=f"measure:{sha256}", priority=PRIORITY_BULK - 25)
        return {"result": "re-measuring"}
    tmp = work_dir("tmp", f"stars_{sha256[:16]}")
    try:
        eng = engine()
        eng.run(f"load {cal}")
        eng.run(f"findstar -out={tmp / 'stars.lst'}")
        _save_stars(cal, parse.star_list(tmp / "stars.lst"), out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"result": "saved" if out.exists() else "no stars"}


@station_task(queue_name="process", priority=PRIORITY_BULK - 30, max_attempts=1)
def backfill_star_maps(limit: int = 10000) -> dict:
    """Queue star maps for every measured light without one (low priority, after new subs and stacks)."""
    queued = 0
    for f in Frame.objects.filter(
        frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED, measurement__state=MeasureState.DONE
    ).only("sha256", "dataset_id")[:limit]:
        if not _star_map_path(f).exists():
            enqueue(star_map, f.sha256, dedupe_key=f"stars:{f.sha256}")
            queued += 1
    return {"queued": queued}


def full_paths(frame: Frame) -> tuple[Path, Path]:
    base = Path(settings.PREVIEWS_DIR) / f"ds{frame.dataset_id or 0}" / "full"
    return base / f"{frame.sha256[:20]}.jpg", base / f"{frame.sha256[:20]}_inspect.jpg"


FULL_VIEW_BUDGET_GB = float(os.environ.get("FULL_VIEW_BUDGET_GB", "20"))  # oldest views go first beyond this


def draw_full_view(frame: Frame, cal: Path | None) -> None:
    """Draw the 100% view and inspector from the calibrated file (or the capture); raises with the reason."""
    from .previews import full_and_inspector

    full, inspect = full_paths(frame)
    if full.exists() and inspect.exists():
        return
    if cal is not None and cal.exists():
        full_and_inspector(cal, full, inspect)
    else:
        src = source_path(frame)
        if src is None:
            raise RuntimeError("The capture isn't on disk any more.")
        if src.suffix.lower() not in (".fit", ".fits", ".fts", ".xisf"):
            raise RuntimeError(f"A {src.suffix} capture can't be drawn at 100%.")
        full_and_inspector(src, full, inspect, raw=True)
    _prune_full_views()


def make_full_view(frame: Frame, cal: Path | None) -> bool:
    """draw_full_view, for work done ahead: True when made, and a failure never fails the measurement."""
    try:
        draw_full_view(frame, cal)
    except Exception as exc:  # noqa: BLE001
        log.warning("Couldn't draw the 100%% view of %s: %s", frame.sha256[:12], exc)
        return False
    return True


def _prune_full_views() -> None:
    root = Path(settings.PREVIEWS_DIR)
    views = sorted(root.glob("ds*/full/*.jpg"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in views)
    budget = FULL_VIEW_BUDGET_GB * 1e9
    for old in views:
        if total <= budget:
            break
        total -= old.stat().st_size
        old.unlink(missing_ok=True)


@station_task(queue_name="process", priority=PRIORITY_LIVE + 10, max_attempts=1)
def full_view(sha256: str) -> dict:
    """The 100% view and aberration inspector of one sub, when asked for one that wasn't made ahead."""
    frame = Frame.objects.get(pk=sha256)
    m = SubMeasurement.objects.filter(frame=frame).first()
    cal = Path(m.calibrated_path) if m and m.calibrated_path else None
    draw_full_view(frame, cal)  # a failure is recorded on the task, and the viewer shows it
    return {"result": "made"}


@station_task(queue_name="process", priority=PRIORITY_BULK - 28, max_attempts=1)
def backfill_full_views(flagged_only: bool = True) -> dict:
    """Make 100% views ahead for the subs Review will ask about (flagged: rejected, down-weighted or near a
    threshold), so opening one is instant; the rest are made when measured or on request."""
    from .models import MachineGrade

    qs = MachineGrade.objects.filter(frame__status=FrameStatus.CATALOGUED)
    if flagged_only:
        from django.db.models import Q

        qs = qs.filter(Q(verdict__in=["reject", "down"]) | Q(near_threshold=True))
    n = 0
    for sha in qs.values_list("frame_id", flat=True):
        f = Frame.objects.filter(pk=sha).only("sha256", "dataset_id").first()
        if f is not None and not full_paths(f)[0].exists():
            enqueue(full_view, sha, dedupe_key=f"full:{sha}", priority=PRIORITY_BULK - 28)
            n += 1
    return {"queued": n}


def master_view_paths(m) -> tuple[Path, Path]:  # noqa: ANN001
    out = Path(m.output_path)
    return out.with_name(out.stem + "_full.jpg"), out.with_name(out.stem + "_inspect.jpg")


@station_task(queue_name="process", priority=PRIORITY_LIVE + 5, max_attempts=1)
def master_view(master_id: int) -> dict:
    """A master's 100% view and aberration inspector (made after stacking, or on request for older masters)."""
    from .models import Master
    from .previews import full_and_inspector

    m = Master.objects.filter(pk=master_id).first()
    if m is None or not m.output_path or not Path(m.output_path).exists():
        return {"result": "no file"}
    full, inspect = master_view_paths(m)
    full_and_inspector(Path(m.output_path), full, inspect)
    return {"result": "made"}


@station_task(queue_name="process", priority=PRIORITY_LIVE + 5, max_attempts=1)
def combined_view(combined_id: int) -> dict:
    """A combined master's 100% view and aberration inspector (made after combining, or on request)."""
    from .models import CombinedMaster
    from .previews import full_and_inspector

    cm = CombinedMaster.objects.filter(pk=combined_id).first()
    if cm is None or not cm.output_path or not Path(cm.output_path).exists():
        return {"result": "no file"}
    full, inspect = master_view_paths(cm)
    full_and_inspector(Path(cm.output_path), full, inspect)
    return {"result": "made"}


PALETTES = {"hoo": {"r": "Hα", "g": "OIII", "b": "OIII"}, "sho": {"r": "SII", "g": "Hα", "b": "OIII"}}


def palette_paths(collection_id: int, project_id: int | None, name: str) -> tuple[Path, Path, Path]:
    base = Path(settings.STACKS_DIR) / "collections" / f"col{collection_id}" / f"{name}_p{project_id or 0}"
    return (
        base.with_name(base.name + "_full.jpg"),
        base.with_name(base.name + "_inspect.jpg"),
        base.with_suffix(".jpg"),
    )


def palette_inputs(collection_id: int, project_id: int | None, name: str) -> dict[str, Path] | None:
    """The current combined master of each filter the palette needs (registered to one framing), or None."""
    from .combine import in_project
    from .models import CombinedMaster, MasterState

    out = {}
    for ch, filt in PALETTES[name].items():
        cm = (
            CombinedMaster.objects.filter(
                collection_id=collection_id,
                filter_norm=filt,
                state=MasterState.CURRENT,
                **in_project(project_id),
            )
            .order_by("-version")
            .first()
        )
        if cm is None or not cm.output_path or not Path(cm.output_path).exists():
            return None
        out[ch] = Path(cm.output_path)
    return out


@station_task(queue_name="process", priority=PRIORITY_LIVE + 5, max_attempts=1)
def palette_view(collection_id: int, project_id: int | None, name: str) -> dict:
    """HOO or SHO at full resolution from the project's combined masters (owner 2026-10-10)."""
    from .previews import palette_and_inspector

    inputs = palette_inputs(collection_id, project_id, name)
    if inputs is None:
        return {"result": "missing combined masters"}
    palette_and_inspector(inputs, *palette_paths(collection_id, project_id, name))
    return {"result": "made"}


@station_task(queue_name="process", priority=PRIORITY_BULK - 26, max_attempts=1)
def rerender_session(dataset_id: int, night_id: int | None) -> dict:
    """Redraw one session's sub previews with one stretch (003 G18): every sub's own stretch is read first, then
    all are drawn with the session's median, so a cloudy sub looks darker beside the others. Subs whose file is
    no longer readable here (an XISF capture with no cached calibrated copy) keep their preview."""
    import json

    import numpy as np

    from .previews import render, screen_planes, stretch_params

    night_q = {"frame__night_id": night_id} if night_id is not None else {"frame__night__isnull": True}
    ms = list(
        SubMeasurement.objects.filter(frame__dataset_id=dataset_id, state=MeasureState.DONE, **night_q)
        .exclude(preview_path="")
        .select_related("frame", "frame__night")
    )
    sources = []
    for m in ms:
        cal = Path(m.calibrated_path) if m.calibrated_path else None
        src, raw = (cal, False) if cal and cal.exists() else (source_path(m.frame), True)
        if src is None or src.suffix.lower() not in (".fit", ".fits", ".fts"):
            continue
        try:
            planes, _mode, _flip = screen_planes(src, raw)
        except Exception:  # noqa: BLE001
            continue
        sources.append((m, src, raw, [stretch_params(pl) for pl in planes]))
    if not sources:
        return {"redrawn": 0}
    for size in {len(x[3]) for x in sources}:  # mono and colour subs (rare in one session) each get their own
        group = [x for x in sources if len(x[3]) == size]
        med = [tuple(float(np.median([g[3][i][k] for g in group])) for k in range(3)) for i in range(size)]
        for m, src, raw, _own in group:
            out = Path(m.preview_path)
            render(src, out, out.with_name(out.stem + "_t.jpg"), raw=raw, params=med)  # type: ignore[arg-type]
        night = ms[0].frame.night.date.isoformat() if ms[0].frame.night else "unknown"
        session = Path(settings.PREVIEWS_DIR) / f"ds{dataset_id}" / "stretch" / f"{night}.json"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text(json.dumps([[list(p) for p in g[3]] for g in group][-60:]))
    return {"redrawn": len(sources)}


@station_task(queue_name="process", priority=PRIORITY_BULK - 27, max_attempts=1)
def rerender_all_sessions() -> dict:
    """Queue a one-stretch redraw for every session (one job each, so the workers share them)."""
    pairs = set(
        Frame.objects.filter(
            frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED, measurement__state=MeasureState.DONE
        ).values_list("dataset_id", "night_id")
    )
    for ds, night in pairs:
        if ds:
            enqueue(rerender_session, ds, night, dedupe_key=f"rerender:{ds}:{night}")
    return {"sessions": len(pairs)}
