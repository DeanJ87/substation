"""Watcher (research R4; T049): inotify events where they arrive plus scheduled sweeps, as a leased singleton.

Only the holder of the `watcher` lease watches and sweeps, so any number of worker containers can run
(`docker compose up --scale worker=N`); if the holder stops renewing, another takes over within ~15 s.
Libraries with recent activity are swept every `sweep_interval_active_s` (60 s), others every
`sweep_interval_idle_s` (15 min); a rescan request from the API triggers an immediate sweep.
"""

from __future__ import annotations

import logging
import os
import queue
import socket
import threading
import time
from datetime import timedelta
from pathlib import Path

from django.db import OperationalError, close_old_connections
from django.utils import timezone
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from apps.catalogue.models import Copy
from apps.catalogue.services.ignore import PathRules
from apps.libraries.discovery import discover_libraries
from apps.libraries.models import Library
from substation.tasks.lease import acquire, release

from .headers import is_image_name
from .pathcheck import check_path, skip_dir
from .sweep import sweep_library

log = logging.getLogger("substation.watcher")
LEASE = "watcher"
RENEW_S = 5
LEASE_TTL_S = 15  # acquire()'s default
ACTIVE_WINDOW = timedelta(hours=1)
UNREACHABLE_RETRY_S = 15  # an unmounted share, or a capture folder that is still empty: look again soon


def _event_file(lib: Library, abs_path: str) -> tuple[str, os.stat_result] | None:
    """The library-relative path and stat of an event's file, or None when it isn't one to check: outside the
    library (after following links), not an image name or inside a skipped folder (e.g. macOS ._ files, which
    the share may not even let us stat), gone already, unreadable, or not a regular file."""
    rel = os.path.relpath(os.path.realpath(abs_path), os.path.realpath(lib.mount_path))
    if rel.startswith(".."):
        return None
    if not is_image_name(os.path.basename(rel)) or any(skip_dir(p) for p in Path(rel).parts[:-1]):
        return None
    try:
        st = os.stat(abs_path)
    except FileNotFoundError:
        return None  # deleted or moved away; the next sweep records it
    except OSError as e:
        log.warning("Couldn't read %s: %s. The next sweep will try again.", abs_path, e)
        return None
    if not os.path.isfile(abs_path):
        return None
    return rel, st


class _Handler(FileSystemEventHandler):
    def __init__(self, lib_id: int, root: str, q: queue.Queue) -> None:
        self.lib_id, self.root, self.q = lib_id, root, q

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        for p in {getattr(event, "dest_path", None), event.src_path}:
            if p:
                self.q.put((self.lib_id, os.fsdecode(p)))


class Watcher:
    def __init__(self, stop: threading.Event) -> None:
        self.stop = stop
        self.holder = f"{socket.gethostname()}:{os.getpid()}"
        self.events: queue.Queue[tuple[int, str]] = queue.Queue()
        self.observer: BaseObserver | None = None
        self.holding = False
        self.watched: dict[int, str] = {}
        self.next_sweep: dict[int, float] = {}

    # -- inotify -----------------------------------------------------------------------------------
    def _start_observers(self, libs: list[Library]) -> None:
        if self.observer is None:
            self.observer = Observer()
            self.observer.start()
        for lib in libs:
            if lib.pk in self.watched or not lib.enabled:
                continue
            try:
                self.observer.schedule(
                    _Handler(lib.pk, lib.mount_path, self.events), lib.mount_path, recursive=True
                )
                self.watched[lib.pk] = lib.mount_path
            except OSError as exc:  # inotify limits or unsupported filesystem: sweeps still cover it
                log.warning("Not watching %s for events (%s); relying on sweeps.", lib.name, exc)
                self.watched[lib.pk] = lib.mount_path

    def _stop_observers(self) -> None:
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=5)
        self.observer, self.watched = None, {}

    def _drain_events(self) -> None:
        handled: set[tuple[int, str]] = set()
        rules: PathRules | None = None  # loaded once per batch, only if needed
        while True:
            try:
                lib_id, abs_path = self.events.get_nowait()
            except queue.Empty:
                break
            if (lib_id, abs_path) in handled:
                continue
            handled.add((lib_id, abs_path))
            lib = Library.objects.filter(pk=lib_id, enabled=True).first()
            if lib is None:
                continue
            target = _event_file(lib, abs_path)
            if target is None:
                continue
            rel, st = target
            if rules is None:
                rules = PathRules.load()
            check_path(lib, rel, st, Copy.objects.filter(library=lib, rel_path=rel).first(), rules)

    # -- sweeps ------------------------------------------------------------------------------------
    def _due_sweeps(self, libs: list[Library]) -> None:
        now = time.monotonic()
        for lib in libs:
            if not lib.enabled:
                continue
            rescan = lib.rescan_requested_at is not None
            if not rescan and now < self.next_sweep.get(lib.pk, 0):
                continue
            Library.objects.filter(pk=lib.pk).update(rescan_requested_at=None)
            result = sweep_library(lib)
            if not result.complete:
                self.next_sweep[lib.pk] = time.monotonic() + UNREACHABLE_RETRY_S
                continue
            # Files queued by this very sweep have no Copy yet, so they count as activity too.
            active = (
                bool(result.queued or result.moved or result.missing)
                or Copy.objects.filter(
                    library=lib, first_seen_at__gte=timezone.now() - ACTIVE_WINDOW
                ).exists()
            )
            interval = lib.sweep_interval_active_s if active else lib.sweep_interval_idle_s
            self.next_sweep[lib.pk] = time.monotonic() + interval
            if self.stop.is_set():
                return

    def _heartbeat(self) -> None:
        """Keep (or take) the lease every few seconds on its own thread, so a sweep of a big library (minutes)
        doesn't let it lapse: then Activity said "Not watching" and another worker started sweeping too. A busy
        database is retried quietly; the lease is only given up once it has really run
        out, not on one missed renewal."""
        last_ok = 0.0
        while not self.stop.is_set():
            try:
                close_old_connections()
                self.holding = acquire(LEASE, self.holder)
                last_ok = time.monotonic()
            except OperationalError:
                if time.monotonic() - last_ok > LEASE_TTL_S - RENEW_S:
                    self.holding = False
            except Exception:  # noqa: BLE001
                log.exception("Watcher %s couldn't renew its lease.", self.holder)
                self.holding = False
            self.stop.wait(RENEW_S)
        close_old_connections()

    def run(self) -> None:
        log.info("Watcher %s started.", self.holder)
        self.holding = False
        beat = threading.Thread(target=self._heartbeat, name="watcher-lease", daemon=True)
        beat.start()
        holding = False
        try:
            while not self.stop.is_set():
                close_old_connections()
                now_holding = self.holding
                if now_holding and not holding:
                    log.info("Watcher %s holds the lease; watching libraries.", self.holder)
                    self.next_sweep.clear()
                if holding and not now_holding:
                    log.warning("Watcher %s lost the lease; stopping.", self.holder)
                    self._stop_observers()
                holding = now_holding
                if not holding:
                    self.stop.wait(0.5)
                    continue
                try:
                    libs = [lib for lib in discover_libraries() if lib.enabled]
                    self._start_observers(libs)
                    self._drain_events()
                    self._due_sweeps(libs)
                except OperationalError as e:  # a locked database: wait it out, don't exit (2026-10-13)
                    log.warning("Watcher couldn't reach the database (%s); trying again shortly", e)
                    self.stop.wait(5)
                    continue
                self.stop.wait(0.5)
        finally:
            self.stop.set()
            beat.join(timeout=RENEW_S + 1)
            self._stop_observers()
            release(LEASE, self.holder)
            log.info("Watcher %s stopped.", self.holder)


def run_watcher(stop: threading.Event) -> None:
    Watcher(stop).run()
