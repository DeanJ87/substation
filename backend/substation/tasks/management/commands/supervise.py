"""`manage.py supervise`: the container's main process (research R3, contracts/container.md).

Starts and watches uvicorn (web + SSE), the watcher and N workers. N is re-read every 5 s from the
installation settings (falls back to SUBSTATION_WORKERS), so the worker count changes without a restart:
extra workers are started, surplus ones get SIGTERM, finish their current task and exit. Crashed children
restart with backoff. Every 10 s it requeues orphaned tasks and prunes old samples and events.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.libraries.discovery import discover_libraries, seed_installation_settings
from apps.libraries.models import InstallationSettings
from substation.tasks.recovery import prune, requeue_all_running, requeue_orphans

log = logging.getLogger("substation.supervisor")

MANAGE = [sys.executable, str(settings.BASE_DIR / "manage.py")]
MAX_WORKERS = 64


@dataclass
class Child:
    name: str
    argv: list[str]
    proc: subprocess.Popen | None = None
    restarts: int = 0
    next_start: float = 0.0
    retiring: bool = False
    started_at: float = field(default=0.0)
    env: dict | None = None  # extra environment for this child

    def start(self) -> None:
        self.proc = subprocess.Popen(self.argv, env={**os.environ, **self.env} if self.env else None)
        self.started_at = time.monotonic()
        log.info("Started %s (pid %s)", self.name, self.proc.pid)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


def measure_work() -> dict:
    """Bytes in the work folder by part (calibrated cache, stacks in progress, other), for the Activity disk readout
    and the stacking budget (005 T004). The API can't see this folder, so the supervisor measures it."""
    from pathlib import Path

    from django.utils import timezone

    from apps.libraries.models import InstallationSettings
    from apps.processing.masters import _dir_bytes

    root = Path(settings.WORK_DIR)
    parts = {"calibrated": _dir_bytes(root / "calibrated"), "stacking": _dir_bytes(root / "integrations")}
    total = _dir_bytes(root)
    used = {
        **parts,
        "other": max(total - sum(parts.values()), 0),
        "total": total,
        "at": timezone.now().isoformat(),
    }
    InstallationSettings.objects.filter(pk=InstallationSettings.load().pk).update(work_used=used)
    return used


class Command(BaseCommand):
    help = "Run the web server, watcher and workers, and keep them running."

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument("--no-web", action="store_true")
        parser.add_argument("--no-watcher", action="store_true")

    def handle(self, *args, **options) -> None:
        logging.basicConfig(level=logging.INFO)
        self.running = True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

        n = requeue_all_running(socket.gethostname()[:24])
        if n:
            log.info("Requeued %s task(s) left running before the restart.", n)
        seed_installation_settings()
        if not os.environ.get("SUBSTATION_ONLY_QUEUES"):  # the finisher doesn't mount the libraries
            discover_libraries()
        elif "finish" in os.environ.get("SUBSTATION_ONLY_QUEUES", ""):
            # say what this finisher can run, for Settings (spec 010)
            from apps.processing.postprocess import check_tools
            from substation.tasks import enqueue

            enqueue(check_tools, dedupe_key="post-tools-check")

        port = os.environ.get("SUBSTATION_PORT", "8080")
        fixed: list[Child] = []
        if not options["no_web"]:
            fixed.append(
                Child(
                    "web",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "substation.asgi:application",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        port,
                        "--proxy-headers",
                    ],
                )
            )
        if not options["no_watcher"]:
            fixed.append(Child("watcher", [*MANAGE, "run_watcher"]))
        if "finish" in os.environ.get("SUBSTATION_ONLY_QUEUES", ""):
            # quick finisher jobs (check tools, activate RC-Astro) never wait behind a long post-processing run
            # (owner 2026-10-12: an activation code sat queued behind a 10-minute denoise)
            fixed.append(
                Child(
                    "control",
                    [
                        *MANAGE,
                        "run_worker",
                        "--id",
                        f"{socket.gethostname()[:24]}-control",
                        "--heavy-slots",
                        "1",
                    ],
                    env={"SUBSTATION_ONLY_QUEUES": "finish_ctl"},
                )
            )
        workers: dict[int, Child] = {}
        # Worker ids must be unique across containers (compose --scale worker=N): prefix with the hostname,
        # which Docker sets to the container id.
        host = socket.gethostname()[:24]
        last_housekeeping = 0.0
        last_measure = 0.0
        started = time.monotonic()

        for c in fixed:
            c.start()
        while self.running:
            wanted, heavy = self._desired()
            # scale up
            for i in range(wanted):
                if i not in workers:
                    workers[i] = Child(
                        f"worker-{i}",
                        [*MANAGE, "run_worker", "--id", f"{host}-worker-{i}", "--heavy-slots", str(heavy)],
                    )
                    workers[i].start()
            # scale down: surplus workers finish their current task, then exit
            for i, c in list(workers.items()):
                if i >= wanted and not c.retiring and c.alive():
                    c.retiring = True
                    c.proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
                    log.info("Retiring %s", c.name)
                if c.retiring and not c.alive():
                    del workers[i]
            # restart crashed children
            for c in [*fixed, *[w for w in workers.values() if not w.retiring]]:
                if not c.alive() and time.monotonic() >= c.next_start:
                    if c.proc is not None:
                        c.restarts += 1
                        delay = min(2**c.restarts, 60) if time.monotonic() - c.started_at < 60 else 1
                        c.next_start = time.monotonic() + delay
                        log.warning("%s exited with %s; restarting in %ss", c.name, c.proc.returncode, delay)
                        c.proc = None
                        continue
                    c.start()
            if time.monotonic() - last_housekeeping > 10:
                try:
                    # a redeploy's stopped tasks surface as orphans just after start: requeue, don't fail them
                    requeue_orphans(lenient=time.monotonic() - started < 300)  # past STALE_HEARTBEAT_S
                    prune()
                    if not os.environ.get("SUBSTATION_ONLY_QUEUES"):
                        discover_libraries()
                except Exception:  # noqa: BLE001
                    log.exception("Housekeeping failed")
                last_housekeeping = time.monotonic()
            if time.monotonic() - last_measure > 300:
                try:
                    measure_work()
                except Exception:  # noqa: BLE001
                    log.exception("Measuring the work folder failed")
                try:
                    from apps.processing.masters import auto_stacks

                    auto_stacks()
                except Exception:  # noqa: BLE001
                    log.exception("Automatic stacks failed")
                try:  # the bin's daily tidy (spec 011): bin long-rejected subs, delete what's past its date
                    from apps.catalogue.services.binning import tidy_due
                    from apps.ingest.tasks.bin import tidy_bin
                    from substation.tasks import enqueue as _enqueue

                    if not os.environ.get("SUBSTATION_ONLY_QUEUES") and tidy_due():
                        _enqueue(tidy_bin, dedupe_key="tidy-bin")
                except Exception:  # noqa: BLE001
                    log.exception("Queueing the bin's tidy failed")
                last_measure = time.monotonic()
            close_old_connections()
            time.sleep(1)

        log.info("Stopping all processes")
        everyone = [*fixed, *workers.values()]
        for c in everyone:
            if c.alive():
                c.proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
        # a redeploy stops the container: running stacks finish first, up to the container's stop grace period
        # (005-DR-23); SUBSTATION_STOP_GRACE_S is set a little under it so nothing is killed mid-write
        deadline = time.monotonic() + int(os.environ.get("SUBSTATION_STOP_GRACE_S", "30"))
        for c in everyone:
            if c.proc is not None:
                try:
                    c.proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
                except subprocess.TimeoutExpired:
                    c.proc.kill()

    def _desired(self) -> tuple[int, int]:
        s = InstallationSettings.load()
        count = s.worker_count if s.worker_count is not None else settings.SUBSTATION_WORKERS
        if os.environ.get("SUBSTATION_ONLY_QUEUES"):  # a dedicated container (the finisher) sizes itself
            count = settings.SUBSTATION_WORKERS
        return max(1, min(int(count), MAX_WORKERS)), max(1, s.siril_heavy_slots)

    def _stop(self, signum, frame) -> None:  # noqa: ANN001, ARG002
        self.running = False
