"""Master post-processing (spec 010): after a master integrates, an optional chain of finishing tools —
GraXpert background extraction, BlurXTerminator, NoiseXTerminator (or GraXpert denoise), StarXTerminator — each
writing its own linear 32-bit stage beside the master, which is never modified. A tool that isn't installed or
licensed is skipped with a plain reason; the chain never fails the master.

The tools are separate programs the admin installs on the worker (RC-Astro's are proprietary and licensed to the
user, so they are never bundled). This module is the one place that calls them (constitution amendment in the
plan: a second adapter boundary beside Siril's)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from django.utils import timezone

from substation.tasks import PRIORITY_BULK, report_progress, station_task

log = logging.getLogger("substation.processing")

TOOL_NAMES = {"graxpert": "GraXpert", "rc_astro": "RC-Astro", "substation": "SubStation"}

STEP_NAMES = {
    "background": "Background extracted",
    "deconvolve": "Deconvolved",
    "denoise": "Denoised",
    "starless": "Starless",
}


def _exe(configured: str, *names: str) -> str | None:
    """A configured path is used as given (never swapped for another install); otherwise the first name found."""
    if configured:
        return configured if Path(configured).is_file() or shutil.which(configured) else None
    for n in names:
        if n and (shutil.which(n) or Path(n).is_file()):
            return shutil.which(n) or n
    return None


_licensed: dict[str, bool] = {}


def rc_licensed(exe: str) -> bool:
    """RC-Astro's CLI runs without a licence but refuses to work; ask it once per process."""
    if exe not in _licensed:
        try:
            r = subprocess.run([exe, "bxt", "--help"], capture_output=True, text=True, timeout=120)
            _licensed[exe] = "license is required" not in (r.stdout + r.stderr).lower()
        except (OSError, subprocess.TimeoutExpired):
            _licensed[exe] = False
    return _licensed[exe]


def readiness(cfg: dict) -> dict:
    """Which tools this worker can run, with a plain reason when not."""
    gx = _exe(cfg.get("graxpert", ""), "GraXpert-linux", "graxpert", "GraXpert")
    import os

    rc = _exe(
        cfg.get("rc_astro", ""),
        os.environ.get("SUBSTATION_RC_ASTRO", ""),
        "/opt/finish/rc-astro/rc-astro",  # where the finisher unpacks it
        "rc-astro",
    )
    licensed = bool(rc) and rc_licensed(rc or "")
    out = {
        "graxpert": {
            "ready": bool(gx),
            "path": gx or "",
            "reason": "" if gx else "GraXpert isn't installed on this worker.",
        },
        "rc_astro": {
            "ready": licensed,
            "path": rc or "",
            "reason": ""
            if licensed
            else (
                "RC-Astro isn't activated on this finisher: paste an activation code in Settings → Processing."
                if rc
                else "RC-Astro's tools aren't installed on this worker."
            ),
        },
    }
    return out


def _tool_for(step: str, ready: dict) -> str | None:
    if step == "background":
        return "graxpert" if ready["graxpert"]["ready"] else None
    if step in ("deconvolve", "starless"):
        return "rc_astro" if ready["rc_astro"]["ready"] else None
    if step == "denoise":  # NoiseXTerminator when there, else GraXpert's denoise (spec 010 assumptions)
        return (
            "rc_astro" if ready["rc_astro"]["ready"] else ("graxpert" if ready["graxpert"]["ready"] else None)
        )
    return None


def command(step: dict, tool: str, exe: str, src: Path, out: Path, gpu: bool) -> list[str]:
    """The command line for one step. GraXpert takes `-output` without an extension; RC-Astro an output folder."""
    s = step["step"]
    if tool == "graxpert":
        base = [
            exe,
            str(src),
            "-cli",
            "-output",
            str(out.with_suffix("")),
            "-gpu",
            "true" if gpu else "false",
        ]
        if s == "background":
            return [
                *base,
                "-cmd",
                "background-extraction",
                "-correction",
                str(step.get("correction", "Subtraction")),
                "-smoothing",
                str(step.get("smoothing", 0.1)),
            ]
        return [*base, "-cmd", "denoising", "-strength", str(step.get("amount", 0.5))]
    engine = [] if gpu else ["--engine", "cpu"]
    if s == "deconvolve":
        return [
            exe,
            "bxt",
            str(src),
            "--output",
            str(out.parent),
            "--depth",
            "32F",
            *engine,
            "--sharpen-stars",
            str(step.get("sharpen_stars", 0.25)),
            "--adjust-star-halos",
            str(step.get("adjust_halos", 0.0)),
            "--sharpen-nonstellar",
            str(step.get("sharpen_nonstellar", 0.5)),
            "--auto-nonstellar-radius",
        ]
    if s == "denoise":
        return [exe, "nxt", str(src), "--output", str(out.parent), "--depth", "32F", *engine]
    return [exe, "sxt", str(src), "--output", str(out.parent), "--depth", "32F", *engine]


def _newest_image(folder: Path, since: float) -> Path | None:
    files = [
        p
        for p in folder.iterdir()
        if p.suffix.lower() in (".fit", ".fits", ".tif", ".tiff", ".xisf") and p.stat().st_mtime >= since
    ]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def preflight(master_path: Path, out_dir: Path) -> str:
    """Why the chain can't run here, in plain words, or "" when it can. The finisher may be another container
    (or machine) with its own mounts and user, so these are the usual ways it goes wrong."""
    import os

    if not master_path.exists():
        return f"The master isn't visible to this worker ({master_path}). Is /data/substation mounted here?"
    if not os.access(master_path, os.R_OK):
        return f"This worker can't read the master ({master_path}): check the mount's permissions for uid {os.getuid()}."
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / f".write-test-{uuid.uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        return f"This worker can't write beside the master ({out_dir}): {exc.strerror or exc}."
    return ""


def edge_box(data, frac: float = 0.02) -> tuple[int, int, int, int] | None:  # noqa: ANN001
    """The rectangle every sub covered: registration leaves a ragged border of zeros (or NaN) where frames from
    other nights didn't reach, and background extraction then treats it as sky (M81 Hα, 2026-10-12: dark bands
    and blotches along the edges after GraXpert, BXT and NXT). Rows and columns with more than `frac` empty
    pixels are trimmed from each side. None when there's nothing to trim."""
    import numpy as np

    a = np.asarray(data)
    plane = a.reshape(-1, a.shape[-2], a.shape[-1]).min(axis=0) if a.ndim == 3 else a
    # work on a reduced copy: edges are found to within a few pixels, fast on a 26 MP master
    step = max(1, min(plane.shape) // 1000)
    empty = (~np.isfinite(plane) | (plane <= 0))[::step, ::step]
    h, w = empty.shape
    t, b, lft, r = 0, h, 0, w
    # peel the emptiest edge until every edge is clean; borders that overlap (top and right) peel in turn
    while b - t > h // 2 and r - lft > w // 2:
        edges = {
            "t": empty[t, lft:r].mean(),
            "b": empty[b - 1, lft:r].mean(),
            "l": empty[t:b, lft].mean(),
            "r": empty[t:b, r - 1].mean(),
        }
        worst = max(edges, key=lambda k: edges[k])
        if edges[worst] <= frac:
            break
        if worst == "t":
            t += 1
        elif worst == "b":
            b -= 1
        elif worst == "l":
            lft += 1
        else:
            r -= 1
    if (t, b, lft, r) == (0, h, 0, w) or b - t <= h // 2 or r - lft <= w // 2:
        return None
    H, W = plane.shape
    return t * step, min(H, b * step), lft * step, min(W, r * step)


def trim_edges(src: Path, out: Path) -> dict | None:
    """Write the master without its registration border (a FITS crop, data untouched otherwise)."""
    from astropy.io import fits

    with fits.open(src, memmap=False) as hl:
        hdu = next(h for h in hl if h.data is not None)
        box = edge_box(hdu.data)
        if box is None:
            return None
        t, b, lft, r = box
        data = hdu.data[..., t:b, lft:r]
        header = hdu.header.copy()
    header["HISTORY"] = f"SubStation: trimmed registration edges to rows {t}:{b}, columns {lft}:{r}"
    out.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=data, header=header).writeto(out, overwrite=True)
    h, w = hdu.data.shape[-2:]
    return {"rows": [t, b], "cols": [lft, r], "of": [h, w]}


def run_chain(master_path: Path, cfg: dict, out_dir: Path) -> list[dict]:
    """Run the enabled steps in order, each on the last good stage. Returns one record per step."""
    ready = readiness(cfg)
    problem = preflight(master_path, out_dir)
    if problem:
        return [{"step": "preflight", "label": "Before starting", "state": "failed", "reason": problem}]
    current = master_path
    stages: list[dict] = []
    if cfg.get("trim_edges", True) and master_path.suffix.lower() in (".fit", ".fits", ".fts"):
        trimmed = out_dir / "step0_trim" / f"{master_path.stem}_trimmed.fits"
        try:
            box = trim_edges(master_path, trimmed)
        except Exception as exc:  # noqa: BLE001 — a master we can't read is the tools' problem to report
            box = None
            log.warning("Couldn't trim %s: %s", master_path, exc)
        if box:
            r, c, (h, w) = box["rows"], box["cols"], box["of"]
            stages.append(
                {
                    "step": "trim",
                    "label": "Edges trimmed",
                    "state": "done",
                    "tool": "substation",
                    "path": str(trimmed),
                    "seconds": 0,
                    "input": master_path.name,
                    "params": {"kept": f"{r[1] - r[0]}×{c[1] - c[0]} of {h}×{w}"},
                }
            )
            current = trimmed
    steps = [s for s in cfg.get("steps", []) if s.get("enabled")]
    for i, step in enumerate(steps):
        name = step["step"]
        tool = _tool_for(name, ready)
        rec: dict = {
            "step": name,
            "label": STEP_NAMES.get(name, name),
            "input": current.name,
            "params": {k: v for k, v in step.items() if k not in ("step", "enabled")},
        }
        if tool is None:
            rec |= {
                "state": "skipped",
                "reason": (ready["rc_astro"] if name != "background" else ready["graxpert"])["reason"],
            }
            stages.append(rec)
            report_progress((i + 1) / max(1, len(steps)), f"{rec['label']}: skipped ({rec['reason']})")
            continue
        # one step at a time, each on the previous step's result (owner: GraXpert, then BXT, then NXT)
        report_progress(i / max(1, len(steps)), f"{rec['label']}: running {TOOL_NAMES[tool]}")
        work = out_dir / f"step{i + 1}_{name}"
        work.mkdir(exist_ok=True)
        target = work / f"{master_path.stem}_{name}.fits"
        cmd = command(step, tool, ready[tool]["path"], current, target, bool(cfg.get("gpu", True)))
        t = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=int(cfg.get("timeout_s", 3600)))
            made = target if target.exists() else _newest_image(work, t)
            if r.returncode != 0 or made is None:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["no output"]
                rec |= {"state": "failed", "reason": f"{tool} stopped: {tail[0][:200]}"}
            else:
                rec |= {
                    "state": "done",
                    "tool": tool,
                    "path": str(made),
                    "seconds": round(time.time() - t, 1),
                }
                current = made
        except subprocess.TimeoutExpired:
            rec |= {"state": "failed", "reason": f"Took longer than {cfg.get('timeout_s', 3600)} s."}
        except OSError as exc:
            rec |= {"state": "failed", "reason": f"Couldn't start {tool}: {exc}"}
        rec["command"] = " ".join(cmd[1:])  # no licence or path secrets are on the command line
        stages.append(rec)
        report_progress(
            (i + 1) / max(1, len(steps)),
            f"{rec['label']}: done with {TOOL_NAMES[tool]} in {rec['seconds']:g} s"
            if rec.get("state") == "done"
            else f"{rec['label']}: failed ({rec.get('reason', '')})",
        )
    return stages


def image_stats(path: Path) -> dict:
    """Numbers to compare versions by (owner 2026-10-12): sky background
    and noise in ADU (16-bit scale), the brightest signal, and their ratio. Noise is from the sky's median absolute
    deviation, so stars and the galaxy don't count as noise."""
    import numpy as np

    from .imaging import read_data

    a = read_data(path)
    sample = a[:: max(1, a.shape[0] // 1500), :: max(1, a.shape[1] // 1500)]
    sample = sample[np.isfinite(sample)]
    bg = float(np.median(sample))
    noise = float(np.median(np.abs(sample - bg)) * 1.4826)
    peak = float(np.percentile(sample, 99.9))
    return {
        "background_adu": round(bg, 2),
        "noise_adu": round(noise, 3),
        "peak_adu": round(peak, 1),
        "snr": round((peak - bg) / noise, 1) if noise > 0 else None,
    }


def stage_views(master_path: Path, stages: list[dict], run: dict | None = None) -> None:
    """Each finished stage's preview and 100% view, drawn with the master's own stretch so versions compare like
    for like when tabbing through them at 100% (owner 2026-10-12)."""
    from .previews import full_and_inspector, master_stretch, render

    try:
        params = master_stretch(master_path)
    except Exception:  # noqa: BLE001 — fall back to each stage's own stretch
        params = None
    if run is not None:
        try:
            run["original_stats"] = image_stats(master_path)
        except Exception:  # noqa: BLE001
            run["original_stats"] = {}
    for st in stages:
        if st.get("state") == "done" and str(st.get("path", "")).lower().endswith((".fit", ".fits")):
            p = Path(st["path"])
            try:
                st["stats"] = image_stats(p)
                render(p, p.with_suffix(".jpg"), p.with_name(p.stem + "_t.jpg"), params=params)
                st["preview"] = str(p.with_suffix(".jpg"))
                full = p.with_name(p.stem + "_full.jpg")
                full_and_inspector(p, full, p.with_name(p.stem + "_inspect.jpg"), params=params)
                st["full"] = str(full)
            except Exception as exc:  # noqa: BLE001
                st["preview_error"] = str(exc)[:200]


@station_task(queue_name="process", priority=PRIORITY_BULK + 5, max_attempts=1)
def redraw_post_views(master_id: int) -> dict:
    """Redraw a master's existing post-processing stages with its stretch, at 100% too (older runs)."""
    from .models import Master

    m = Master.objects.get(pk=master_id)
    report = dict(m.report or {})
    runs = report.get("post_runs", [])
    if not runs or not m.output_path:
        return {"result": "nothing to redraw"}
    for run in runs[-2:]:  # the latest runs; older ones keep their thumbnails
        stage_views(Path(m.output_path), run.get("stages", []), run)
    Master.objects.filter(pk=m.pk).update(report=report)
    return {"result": "redrawn", "runs": min(2, len(runs))}


@station_task(queue_name="finish", priority=PRIORITY_BULK + 4, max_attempts=3)  # helpers can restart mid-job
def postprocess_master(master_id: int, overrides: dict | None = None) -> dict:
    """Spec 010 US1/US3: run the chain on a master (from the untouched master, every time)."""
    from .config import _merge, processing_settings
    from .models import Master

    m = Master.objects.get(pk=master_id)
    if not m.output_path:
        return {"result": "no master file"}
    cfg = _merge(processing_settings()["post"], overrides or {})
    src = Path(m.output_path)
    run_no = len((m.report or {}).get("post_runs", [])) + 1
    out_dir = src.parent / f"{src.stem}_post{run_no}"
    started = timezone.now()
    stages = run_chain(src, cfg, out_dir)
    run_stats: dict = {}
    stage_views(src, stages, run_stats)
    run = {
        "run": run_no,
        "started_at": started.isoformat(),
        "finished_at": timezone.now().isoformat(),
        "stages": stages,
        "settings": cfg,
        **run_stats,
    }
    m.refresh_from_db()
    report = dict(m.report or {})
    report["post_runs"] = [*report.get("post_runs", []), run]
    Master.objects.filter(pk=m.pk).update(report=report)
    from substation.events.emit import emit

    emit("master.updated", {"dataset_id": m.dataset_id, "master_id": m.pk, "state": m.state})
    done = sum(1 for s in stages if s.get("state") == "done")
    return {"run": run_no, "done": done, "skipped": sum(1 for s in stages if s.get("state") == "skipped")}


def _save_tool_status(status: dict) -> None:
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    p = dict(s.processing or {})
    p["post_tools"] = status
    InstallationSettings.objects.filter(pk=s.pk).update(processing=p)


def _tool_status(cfg: dict, note: str = "") -> dict:
    import socket

    ready = readiness(cfg)
    return {
        "checked_at": timezone.now().isoformat(),
        "host": socket.gethostname(),
        "note": note,
        **{k: {"ready": v["ready"], "reason": v["reason"]} for k, v in ready.items()},
    }


@station_task(queue_name="finish_ctl", priority=PRIORITY_BULK + 30, max_attempts=1)
def check_tools() -> dict:
    """What the finisher can run now, recorded for Settings (the API can't see the finisher's tools itself)."""
    from .config import processing_settings

    status = _tool_status(processing_settings()["post"])
    _save_tool_status(status)
    return {k: v["ready"] for k, v in status.items() if isinstance(v, dict)}


@station_task(queue_name="finish_ctl", priority=PRIORITY_BULK + 30, max_attempts=1)
def activate_rc_astro(code: str) -> dict:
    """Owner 2026-10-12: activate RC-Astro from the web. Activation codes come from the RC-Astro account page and
    expire in 30 minutes; the licence is tied to this finisher (its hostname and network address are pinned)."""
    import re

    from .config import processing_settings

    cfg = processing_settings()["post"]
    exe = readiness(cfg)["rc_astro"]["path"]
    if not exe:
        note = "RC-Astro's tools aren't installed on this finisher."
    elif not re.fullmatch(r"[A-Za-z0-9]{4}-[A-Za-z0-9]{4}", code.strip()):
        note = "That doesn't look like an activation code (four letters or digits, a dash, four more)."
    else:
        try:
            r = subprocess.run(
                [exe, "license", code.strip()],
                capture_output=True,
                text=True,
                timeout=1800,
                stdin=subprocess.DEVNULL,
            )
            out = (r.stdout + r.stderr).replace("\r", "\n")
            activated = [m for m in re.findall(r"- (\w+): Activated", out)]
            note = (
                f"Activated {', '.join(activated)}."
                if activated
                else next(
                    (ln.strip() for ln in out.splitlines() if "not" in ln.lower() or "expired" in ln.lower()),
                    "RC-Astro didn't confirm the activation.",
                )
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            note = f"Couldn't run RC-Astro: {exc}"
    _licensed.clear()  # ask RC-Astro again
    status = _tool_status(cfg, note)
    _save_tool_status(status)
    return {"note": note, "rc_astro": status["rc_astro"]["ready"]}
