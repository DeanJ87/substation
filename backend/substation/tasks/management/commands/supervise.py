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
from collections.abc import Callable
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
        _startup()

        fixed = _fixed_children(web=not options["no_web"], watcher=not options["no_watcher"])
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
            _scale(workers, wanted, heavy, host)
            _restart_crashed([*fixed, *[w for w in workers.values() if not w.retiring]])
            if time.monotonic() - last_housekeeping > 10:
                _housekeeping(lenient=time.monotonic() - started < 300)  # past STALE_HEARTBEAT_S
                last_housekeeping = time.monotonic()
            if time.monotonic() - last_measure > 300:
                for what, job in _periodic_jobs(host):
                    try:
                        job()
                    except Exception:  # noqa: BLE001
                        log.exception("%s failed", what)
                last_measure = time.monotonic()
            close_old_connections()
            time.sleep(1)

        log.info("Stopping all processes")
        _stop_all([*fixed, *workers.values()])

    def _desired(self) -> tuple[int, int]:
        s = InstallationSettings.load()
        count = s.worker_count if s.worker_count is not None else settings.SUBSTATION_WORKERS
        if os.environ.get("SUBSTATION_ONLY_QUEUES"):  # a dedicated container (the finisher) sizes itself
            count = settings.SUBSTATION_WORKERS
        return max(1, min(int(count), MAX_WORKERS)), max(1, s.siril_heavy_slots)

    def _stop(self, signum, frame) -> None:  # noqa: ANN001, ARG002
        self.running = False


def _only_queues() -> str:
    return os.environ.get("SUBSTATION_ONLY_QUEUES", "")


def _startup() -> None:
    n = requeue_all_running(socket.gethostname()[:24])
    if n:
        log.info("Requeued %s task(s) left running before the restart.", n)
    seed_installation_settings()
    if not _only_queues():  # the finisher doesn't mount the libraries
        discover_libraries()
    elif "finish" in _only_queues():
        # say what this finisher can run, for Settings (spec 010)
        from apps.processing.postprocess import check_tools
        from substation.tasks import enqueue

        enqueue(check_tools, dedupe_key="post-tools-check")


def _fixed_children(*, web: bool, watcher: bool) -> list[Child]:
    port = os.environ.get("SUBSTATION_PORT", "8080")
    fixed: list[Child] = []
    if web:
        uvicorn = ["-m", "uvicorn", "substation.asgi:application", "--host", "0.0.0.0", "--port", port]
        fixed.append(Child("web", [sys.executable, *uvicorn, "--proxy-headers"]))
    if watcher:
        fixed.append(Child("watcher", [*MANAGE, "run_watcher"]))
    if "finish" in _only_queues():
        # quick finisher jobs (check tools, activate RC-Astro) never wait behind a long post-processing run
        # (owner 2026-10-12: an activation code sat queued behind a 10-minute denoise)
        worker_id = f"{socket.gethostname()[:24]}-control"
        fixed.append(
            Child(
                "control",
                [*MANAGE, "run_worker", "--id", worker_id, "--heavy-slots", "1"],
                env={"SUBSTATION_ONLY_QUEUES": "finish_ctl"},
            )
        )
    return fixed


def _scale(workers: dict[int, Child], wanted: int, heavy: int, host: str) -> None:
    """Start missing workers; surplus ones finish their current task, then exit."""
    for i in range(wanted):
        if i not in workers:
            argv = [*MANAGE, "run_worker", "--id", f"{host}-worker-{i}", "--heavy-slots", str(heavy)]
            workers[i] = Child(f"worker-{i}", argv)
            workers[i].start()
    for i, c in list(workers.items()):
        if i >= wanted and not c.retiring and c.alive():
            c.retiring = True
            c.proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
            log.info("Retiring %s", c.name)
        if c.retiring and not c.alive():
            del workers[i]


def _restart_crashed(children: list[Child]) -> None:
    """A child that exited is restarted, after a backoff if it keeps dying within a minute of starting."""
    for c in children:
        if c.alive() or time.monotonic() < c.next_start:
            continue
        if c.proc is not None:
            c.restarts += 1
            delay = min(2**c.restarts, 60) if time.monotonic() - c.started_at < 60 else 1
            c.next_start = time.monotonic() + delay
            log.warning("%s exited with %s; restarting in %ss", c.name, c.proc.returncode, delay)
            c.proc = None
            continue
        c.start()


def _housekeeping(*, lenient: bool) -> None:
    try:
        # a redeploy's stopped tasks surface as orphans just after start: requeue, don't fail them
        requeue_orphans(lenient=lenient)
        prune()
        if not _only_queues():
            discover_libraries()
    except Exception:  # noqa: BLE001
        log.exception("Housekeeping failed")


def _auto_builds(
    host: str,
) -> None:  # 002-DR-23: masters from settled calibration sessions; one container at a time
    from apps.processing.calibration import auto_builds
    from substation.tasks.lease import acquire

    if not _only_queues() and acquire("auto-builds", host, ttl_s=240):
        auto_builds()


def _queue_bin_tidy() -> (
    None
):  # the bin's daily tidy (spec 011): bin long-rejected subs, delete what's past its date
    from apps.catalogue.services.binning import tidy_due
    from apps.ingest.tasks.bin import tidy_bin
    from substation.tasks import enqueue

    if not _only_queues() and tidy_due():
        enqueue(tidy_bin, dedupe_key="tidy-bin")


def _queue_backup() -> None:  # spec 014: the daily database backup, at the set time
    from substation.backup import backup_due
    from substation.backup_api import backup_database
    from substation.tasks import enqueue

    if not _only_queues() and backup_due():
        enqueue(backup_database, dedupe_key="backup-database")


def _auto_stacks() -> None:
    from apps.processing.masters import auto_stacks

    auto_stacks()


def _periodic_jobs(host: str) -> list[tuple[str, Callable[[], object]]]:
    """Every five minutes; each fails on its own, logged, without stopping the others."""
    return [
        ("Measuring the work folder", measure_work),
        ("Automatic stacks", _auto_stacks),
        ("Automatic calibration builds", lambda: _auto_builds(host)),
        ("Queueing the bin's tidy", _queue_bin_tidy),
        ("Queueing the database backup", _queue_backup),
    ]


def _stop_all(everyone: list[Child]) -> None:
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
