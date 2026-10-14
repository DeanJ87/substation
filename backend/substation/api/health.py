"""GET /api/v1/health: database, libraries and worker status (public; used by Docker health checks)."""

import shutil
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.libraries.models import Library
from substation.api import Router, Schema
from substation.tasks.models import Worker, WorkerState

router = Router(tags=["health"])


class LibraryHealth(Schema):
    name: str
    status: str


class HealthOut(Schema):
    status: str
    database: str
    journal_mode: str
    version: str = ""  # "0.1.0 · poc-substation · 1a2b3c4 · 11 Oct 2026"; empty in a dev checkout
    libraries: list[LibraryHealth]
    workers_alive: int
    disk_free_bytes: int | None
    disk_total_bytes: int | None


@router.get("", response=HealthOut, auth=None)
def health(request):  # type: ignore[no-untyped-def]
    if connection.vendor == "sqlite":
        with connection.cursor() as cur:
            cur.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
    else:
        mode = connection.vendor  # "postgresql"
    cutoff = timezone.now() - timedelta(seconds=30)
    alive = Worker.objects.filter(heartbeat_at__gte=cutoff).exclude(state=WorkerState.STOPPED).count()
    libs = [
        LibraryHealth(name=lib.name, status=lib.status) for lib in Library.objects.filter(enabled=True)
    ]  # watched only
    free: int | None
    total: int | None
    try:
        usage = shutil.disk_usage(settings.STATION_ROOT)
        free, total = usage.free, usage.total
    except OSError:
        free = total = None
    return HealthOut(
        version=settings.SUBSTATION_VERSION,
        status="ok",
        database="ok",
        journal_mode=mode,
        libraries=libs,
        workers_alive=alive,
        disk_free_bytes=free,
        disk_total_bytes=total,
    )
