#!/usr/bin/env python3
"""SubStation post-processing helper (spec 010, owner 2026-10-13).

Runs on a machine with a real GPU — the owner's Mac, natively, so RC-Astro uses CoreML on the Apple GPU (Docker on
macOS can't reach the GPU). It asks SubStation for the next master, downloads it, runs GraXpert → BlurXTerminator →
NoiseXTerminator (and StarXTerminator when switched on), uploads each stage and says when it's done.

    python3 substation_helper.py --url https://substation.example.com   (or set SUBSTATION_URL)

The token comes from SUBSTATION_HELPER_TOKEN or ~/.config/substation/helper.token. Standard library only.
Keep the command lines in step with apps/processing/postprocess.py:command().
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "2"
GRAXPERT = ["/Applications/GraXpert.app/Contents/MacOS/GraXpert", "GraXpert-linux", "graxpert"]
RC_ASTRO = ["/Applications/RC-Astro/CLI/rc-astro", "/opt/finish/rc-astro/rc-astro", "rc-astro"]
LABELS = {
    "background": "Background extracted",
    "deconvolve": "Deconvolved",
    "denoise": "Denoised",
    "starless": "Starless",
}
NAMES = {"graxpert": "GraXpert", "rc_astro": "RC-Astro"}


def find(cands: list[str]) -> str | None:
    for c in filter(None, cands):
        p = shutil.which(c) or (c if Path(c).is_file() and os.access(c, os.X_OK) else None)
        if p:
            return p
    return None


def tools() -> dict:
    # the container entrypoint says where it unpacked each tool; elsewhere the usual install places
    gx = find([os.environ.get("SUBSTATION_GRAXPERT", ""), *GRAXPERT])
    rc = find([os.environ.get("SUBSTATION_RC_ASTRO", ""), *RC_ASTRO])
    licensed = False
    if rc:
        try:
            r = subprocess.run([rc, "bxt", "--help"], capture_output=True, text=True, timeout=120)
            licensed = "license is required" not in (r.stdout + r.stderr).lower()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "graxpert": {
            "ready": bool(gx),
            "reason": "" if gx else "GraXpert isn't installed on this helper.",
            "path": gx,
        },
        "rc_astro": {
            "ready": bool(rc) and licensed,
            "reason": ""
            if rc and licensed
            else (
                "RC-Astro isn't activated on this helper."
                if rc
                else "RC-Astro isn't installed on this helper."
            ),
            "path": rc,
        },
    }


def command(step: dict, tool: str, exe: str, src: Path, out: Path, gpu: bool) -> list[str]:
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


class Api:
    def __init__(self, url: str, token: str, host: str) -> None:
        self.url, self.token, self.host = url.rstrip("/"), token, host

    def _req(
        self, method: str, path: str, body: Any = None, ctype: str = "application/json", **kw: Any
    ) -> Any:
        sep = "&" if "?" in path else "?"
        req = urllib.request.Request(
            f"{self.url}{path}{sep}host={urllib.parse.quote(self.host)}", data=body, method=method
        )
        req.add_header("X-Helper-Token", self.token)
        if body is not None:
            req.add_header("Content-Type", ctype)
        for k, v in kw.get("headers", {}).items():
            req.add_header(k, v)
        return urllib.request.urlopen(req, timeout=kw.get("timeout", 120))

    def post(self, path: str, data: dict) -> dict | None:
        with self._req("POST", path, json.dumps(data).encode()) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def download(self, path: str, dest: Path) -> None:
        with self._req("GET", path, timeout=600) as r, dest.open("wb") as fh:
            shutil.copyfileobj(r, fh, 8 << 20)

    def upload(self, path: str, src: Path) -> None:
        with src.open("rb") as fh:
            req = self._req(
                "POST",
                path,
                body=fh,
                ctype="application/octet-stream",  # type: ignore[arg-type]
                headers={"Content-Length": str(src.stat().st_size)},
                timeout=900,
            )
            req.read()


def _cpu_seconds(t: str) -> float:
    """ps TIME: "1:02.50" (macOS), "00:01:02" or "1-02:03:04" (Linux)."""
    days, _, rest = t.rpartition("-")
    secs = 0.0
    for part in rest.split(":"):
        secs = secs * 60 + float(part)
    return secs + (int(days) * 86400 if days else 0)


class Sampler:
    """CPU % and memory of this helper and the tool it runs (and their children), from `ps`, on macOS and Linux.
    CPU % is CPU time used since the last sample over the time passed: 100% is one core, as on the NAS."""

    def __init__(self) -> None:
        self.last: dict[int, float] = {}
        self.at = time.monotonic()

    def take(self, tool_pid: int | None = None) -> dict | None:
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "pid=,ppid=,rss=,time="], capture_output=True, text=True, timeout=10
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        procs: dict[int, tuple[int, int, float]] = {}
        for line in out.splitlines():
            f = line.split()
            if len(f) == 4:
                with contextlib.suppress(ValueError):
                    procs[int(f[0])] = (int(f[1]), int(f[2]) * 1024, _cpu_seconds(f[3]))
        kids: dict[int, list[int]] = {}
        for pid, (ppid, _, _) in procs.items():
            kids.setdefault(ppid, []).append(pid)

        def tree(root: int) -> list[int]:
            todo, seen = [root], []
            while todo:
                p = todo.pop()
                if p in procs and p not in seen:
                    seen.append(p)
                    todo.extend(kids.get(p, []))
            return seen

        now = time.monotonic()
        wall = max(now - self.at, 0.1)
        cpu = {p: max(procs[p][2] - self.last.get(p, procs[p][2]), 0) / wall * 100 for p in procs}
        self.last, self.at = {p: v[2] for p, v in procs.items()}, now
        mine, tool = tree(os.getpid()), tree(tool_pid) if tool_pid else []
        return {
            "cpu_pct": round(sum(cpu[p] for p in mine), 1),
            "rss_bytes": sum(procs[p][1] for p in mine),
            "tool_cpu_pct": round(sum(cpu[p] for p in tool), 1),
            "tool_rss_bytes": sum(procs[p][1] for p in tool),
        }


SAMPLER = Sampler()


class Beat(threading.Thread):
    """Progress, CPU and memory every 10 s while a job runs, so SubStation shows the helper like a NAS worker
    and knows the job is alive. The reply says whether the job was cancelled."""

    def __init__(self, api: Api, task: str) -> None:
        super().__init__(daemon=True)
        self.api, self.task, self.note, self.fraction, self.stop, self.cancel = (
            api,
            task,
            "",
            0.0,
            threading.Event(),
            False,
        )
        self.tool_pid: int | None = None
        self.command = ""
        self.lock = threading.Lock()

    def say(self, note: str, fraction: float) -> None:
        self.note, self.fraction = note, fraction
        self.send()

    def send(self) -> None:
        with self.lock:
            body = {
                "note": self.note,
                "fraction": self.fraction,
                "command": self.command,
                "sample": SAMPLER.take(self.tool_pid),
            }
        try:
            r = self.api.post(f"/api/v1/helper/tasks/{self.task}/progress", body)
            self.cancel = bool(r and r.get("cancel"))
        except Exception as e:  # noqa: BLE001
            print(f"progress not sent: {e}", file=sys.stderr)

    def run(self) -> None:
        while not self.stop.wait(10):
            self.send()


def newest_image(folder: Path, since: float) -> Path | None:
    files = [
        p for p in folder.iterdir() if p.suffix.lower() in (".fit", ".fits") and p.stat().st_mtime >= since
    ]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def run_tool(cmd: list[str], beat: Beat, timeout: int) -> tuple[int, str]:
    """Run one tool, measured by the heartbeat; stopped at once when the job is cancelled in SubStation."""
    with tempfile.TemporaryFile("w+") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
        with beat.lock:
            beat.tool_pid = p.pid
            beat.command = " ".join([Path(cmd[0]).name, *(Path(c).name if "/" in c else c for c in cmd[1:])])
        beat.send()
        start = time.monotonic()
        try:
            while p.poll() is None:
                if beat.cancel or time.monotonic() - start > timeout:
                    p.terminate()
                    try:
                        p.wait(20)
                    except subprocess.TimeoutExpired:
                        p.kill()
                    raise RuntimeError(
                        "Cancelled in SubStation." if beat.cancel else f"Stopped after {timeout} s."
                    )
                time.sleep(1)
        finally:
            with beat.lock:
                beat.tool_pid, beat.command = None, ""
        log.seek(0)
        return p.returncode, log.read()


def run_job(api: Api, job: dict, ready: dict) -> None:
    tid, cfg = job["task_id"], job["settings"]
    beat = Beat(api, tid)
    beat.start()
    work = Path(tempfile.mkdtemp(prefix="substation-"))
    try:
        beat.say(f"Downloading {job['name']}", 0.02)
        master = work / "master.fits"
        api.download(job["master_url"], master)
        steps = [s for s in cfg.get("steps", []) if s.get("enabled")]
        current, records = master, []
        for i, step in enumerate(steps):
            name = step["step"]
            label = LABELS.get(name, name)
            if name == "background":
                tool = "graxpert" if ready["graxpert"]["ready"] else None
            elif name in ("deconvolve", "starless"):
                tool = "rc_astro" if ready["rc_astro"]["ready"] else None
            else:
                tool = (
                    "rc_astro"
                    if ready["rc_astro"]["ready"]
                    else ("graxpert" if ready["graxpert"]["ready"] else None)
                )
            rec = {
                "step": name,
                "label": label,
                "state": "skipped",
                "input": current.name,
                "params": {k: v for k, v in step.items() if k not in ("step", "enabled")},
            }
            if tool is None:
                rec["reason"] = (ready["graxpert"] if name == "background" else ready["rc_astro"])["reason"]
                beat.say(f"{label}: skipped ({rec['reason']})", (i + 1) / len(steps))
                records.append(rec)
                continue
            beat.say(f"{label}: running {NAMES[tool]}", i / len(steps))
            out_dir = work / f"step{i}_{name}"
            out_dir.mkdir()
            target = out_dir / f"master_{name}.fits"
            cmd = command(step, tool, ready[tool]["path"], current, target, bool(cfg.get("gpu", True)))
            t = time.time()
            code, output = run_tool(cmd, beat, int(cfg.get("timeout_s", 3600)))
            made = target if target.exists() else newest_image(out_dir, t)
            if code != 0 or made is None:
                tail = output.strip().splitlines()[-1:] or ["no output"]
                rec.update(state="failed", reason=f"{tool} stopped: {tail[0][:200]}")
                beat.say(f"{label}: failed ({rec['reason']})", (i + 1) / len(steps))
            else:
                secs = round(time.time() - t, 1)
                beat.say(f"{label}: uploading", (i + 0.9) / len(steps))
                api.upload(f"/api/v1/helper/tasks/{tid}/stage/{i}?step={name}", made)
                rec.update(
                    state="done",
                    tool=tool,
                    seconds=secs,
                    file_name=f"{Path(job['master_file']).stem}_{name}.fits",
                )
                beat.say(f"{label}: done with {NAMES[tool]} in {secs:g} s", (i + 1) / len(steps))
                current = made
            records.append(rec)
        beat.say("Saving the run", 0.98)
        api.post(f"/api/v1/helper/tasks/{tid}/done", {"stages": records})
        print(f"done: {job['name']}")
    except Exception as e:  # noqa: BLE001
        print(f"failed: {job.get('name')}: {e}", file=sys.stderr)
        with contextlib.suppress(Exception):
            api.post(f"/api/v1/helper/tasks/{tid}/fail", {"reason": str(e)[:500]})
    finally:
        beat.stop.set()
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--url", default=os.environ.get("SUBSTATION_URL"), help="SubStation's address (or SUBSTATION_URL)"
    )
    ap.add_argument("--host", default=socket.gethostname().split(".")[0])
    ap.add_argument("--once", action="store_true", help="run at most one job, then exit")
    ap.add_argument("--check", action="store_true", help="report tools to SubStation without taking a job")
    a = ap.parse_args()
    if not a.url:
        ap.error("say where SubStation is: --url https://… or SUBSTATION_URL")
    token = (
        os.environ.get("SUBSTATION_HELPER_TOKEN")
        or (Path.home() / ".config/substation/helper.token").read_text().strip()
    )
    api = Api(a.url, token, a.host)
    print(f"SubStation helper {VERSION} on {a.host} → {a.url}")
    if a.check:
        ready = tools()
        for k, v in ready.items():
            print(f"  {k}: {'ready' if v['ready'] else v['reason']} ({v['path'] or 'not found'})")
        api.post(
            "/api/v1/helper/ping",
            {
                "host": a.host,
                "version": VERSION,
                "tools": {k: {"ready": v["ready"], "reason": v["reason"]} for k, v in ready.items()},
            },
        )
        print("  SubStation: connected")
        return
    while True:
        ready = tools()
        try:
            job = api.post(
                "/api/v1/helper/claim",
                {
                    "host": a.host,
                    "version": VERSION,
                    "tools": {k: {"ready": v["ready"], "reason": v["reason"]} for k, v in ready.items()},
                    "sample": SAMPLER.take(),
                },
            )
        except (urllib.error.URLError, OSError) as e:
            print(f"SubStation unreachable: {e}", file=sys.stderr)
            job = None
        if job:
            print(f"job: {job['name']}")
            run_job(api, job, ready)
            if a.once:
                return
            continue
        if a.once:
            return
        time.sleep(15)


if __name__ == "__main__":
    main()
