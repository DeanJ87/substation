"""`manage.py run_worker --id worker-0`: one queue worker (started by the supervisor)."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from substation.tasks.worker import WorkerProcess


class Command(BaseCommand):
    help = "Run one queue worker until stopped."

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument("--id", required=True)
        parser.add_argument("--heavy-slots", type=int, default=1)
        parser.add_argument("--max-tasks", type=int, default=None, help="exit after N tasks (tests)")

    def handle(self, *args, **options) -> None:
        logging.basicConfig(level=logging.INFO)
        import apps.ingest.tasks  # noqa: F401  (task modules register their options on import)
        import apps.processing.calibration  # noqa: F401
        import apps.processing.masters  # noqa: F401
        import apps.processing.solving  # noqa: F401
        import apps.processing.tasks  # noqa: F401

        worker = WorkerProcess(options["id"], heavy_slots=options["heavy_slots"])
        worker.install_signals()
        worker.run(max_tasks=options["max_tasks"])
