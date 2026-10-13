"""`manage.py run_watcher`: inotify events and scheduled sweeps (full implementation: T049, US1)."""

from __future__ import annotations

import logging
import signal
import threading

from django.core.management.base import BaseCommand

log = logging.getLogger("substation.watcher")


class Command(BaseCommand):
    help = "Watch libraries for new, changed, moved and deleted files."

    def handle(self, *args, **options) -> None:
        logging.basicConfig(level=logging.INFO)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        try:
            from apps.ingest.watcher import run_watcher
        except ImportError:
            log.info("Watcher not implemented yet; idling.")
            stop.wait()
            return
        run_watcher(stop)
