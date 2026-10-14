"""Worker process: claim → run → record, with heartbeats and CPU/RAM samples (research R2, R3; spec 005)."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
import traceback
from datetime import timedelta

import psutil
from django.db import OperationalError, close_old_connections
from django.utils import timezone

from . import Cancelled, Interrupted, Reschedule, current_task_id, shutting_down
from .backend import load_task
from .claim import claim
from .models import ResourceSample, Task, TaskStatus, Worker, WorkerKind, WorkerState

log = logging.getLogger(__name__)

HEARTBEAT_S = 5
SAMPLE_S = 2
IDLE_POLL_S = 0.5
QUEUE_EVENT_S = 2.0  # queue.changed at most this often per worker (events.md)
BACKOFF_BASE_S = 5


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_BASE_S * 2 ** max(attempts - 1, 0), 600))


ENGINE_MARK = "\n--- Siril output ---\n"


def engine_excerpt(exc: BaseException, lines: int = 25) -> str:
    """The engine's own output for a failed Siril command (005 T012), so a failure shows what Siril said and
    not only the Python traceback."""
    from apps.engine.siril import EngineError

    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, EngineError) and seen.log:
            return ENGINE_MARK + f"$ {seen.command}\n" + "\n".join(seen.log[-lines:])
        seen = seen.__cause__ or seen.__context__
    return ""


class WorkerProcess:
    def __init__(self, worker_id: str, heavy_slots: int = 1, kind: str = WorkerKind.WORKER) -> None:
        self.worker_id = worker_id
        self.heavy_slots = heavy_slots
        self.kind = kind
        self.stopping = threading.Event()
        self._last_queue_event: float | None = None
        self._sampler_stop = (
            threading.Event()
        )  # set when run() returns, so sampling never outlives the worker
        self.current: Task | None = None
        self.proc = psutil.Process(os.getpid())

    # -- lifecycle ---------------------------------------------------------------------------------
    def register(self) -> None:
        now = timezone.now()
        Worker.objects.update_or_create(
            pk=self.worker_id,
            defaults={
                "pid": os.getpid(),
                "kind": self.kind,
                "state": WorkerState.IDLE,
                "started_at": now,
                "heartbeat_at": now,
                "current_task": None,
            },
        )

    def install_signals(self) -> None:
        def stop(signum, frame):  # noqa: ANN001, ARG001
            # 005-DR-25: Siril is stopped and the task put back in the queue; it resumes from its checkpoints
            log.info("Worker %s stopping: its task goes back in the queue.", self.worker_id)
            self.stopping.set()
            shutting_down.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

    def sampler(self) -> None:
        """Every 2 s: CPU% and RSS for this process and its children (Siril), plus heartbeats."""
        self.proc.cpu_percent(None)
        children_cpu: dict[int, psutil.Process] = {}
        last_hb = last_prune = 0.0
        while not self._sampler_stop.wait(SAMPLE_S):
            try:
                cpu = self.proc.cpu_percent(None)
                rss = self.proc.memory_info().rss
                ecpu, erss = 0.0, 0
                for child in self.proc.children(recursive=True):
                    if child.pid not in children_cpu:
                        child.cpu_percent(None)
                        children_cpu[child.pid] = child
                        continue
                    try:
                        c, r = child.cpu_percent(None), child.memory_info().rss
                        cpu += c
                        rss += r
                        if "siril" in child.name():
                            ecpu, erss = ecpu + c, erss + r
                    except psutil.Error:
                        children_cpu.pop(child.pid, None)
                now = timezone.now()
                ResourceSample.objects.create(
                    worker_id=self.worker_id,
                    cpu_pct=cpu,
                    rss_bytes=rss,
                    engine_cpu_pct=ecpu,
                    engine_rss_bytes=erss,
                    at=now,
                )
                from apps.engine import siril as _siril

                running = _siril._engine.current if _siril._engine is not None else None
                if running != getattr(self, "_shown_command", None):
                    Worker.objects.filter(pk=self.worker_id).update(
                        engine_command=(running or "")[:300] or None
                    )
                    self._shown_command = running
                if time.monotonic() - last_prune >= 300:  # keep an hour of samples
                    ResourceSample.objects.filter(
                        worker_id=self.worker_id, at__lt=now - timedelta(hours=1)
                    ).delete()
                    last_prune = time.monotonic()
                if time.monotonic() - last_hb >= HEARTBEAT_S:
                    Worker.objects.filter(pk=self.worker_id).update(heartbeat_at=now)
                    if self.current is not None:
                        Task.objects.filter(pk=self.current.pk).update(heartbeat_at=now)
                    last_hb = time.monotonic()
            except Exception:  # noqa: BLE001 (sampling must never kill the worker)
                log.exception("Resource sampling failed")
            finally:
                close_old_connections()

    def _heavy_slots(self) -> int:
        """Stacking slots as set now in Settings (005 T002), so a change applies at the next claim."""
        try:
            from apps.libraries.models import InstallationSettings

            return max(1, InstallationSettings.load().siril_heavy_slots or self.heavy_slots)
        except Exception:  # noqa: BLE001 — a settings read must never stop the worker
            return self.heavy_slots

    def run(self, max_tasks: int | None = None) -> int:
        self.register()
        sampler = threading.Thread(target=self.sampler, name="sampler", daemon=True)
        sampler.start()
        done = 0
        while not self.stopping.is_set():
            close_old_connections()
            try:
                task = claim(self.worker_id, self._heavy_slots())
                if task is None:
                    Worker.objects.filter(pk=self.worker_id).update(state=WorkerState.IDLE, current_task=None)
                    self._queue_changed(final=True)
            except OperationalError as e:
                # the database can be locked for minutes while the disk it shares with stacks stalls: wait it out
                # rather than exit (an exit restarts every worker and orphans what they were running, 2026-10-13)
                log.warning("Couldn't reach the queue (%s); trying again shortly", e)
                self.stopping.wait(5)
                continue
            if task is None:
                if max_tasks is not None:
                    break
                self.stopping.wait(IDLE_POLL_S)
                continue
            self.execute(task)
            self._queue_changed()
            done += 1
            if max_tasks is not None and done >= max_tasks:
                break
        Worker.objects.filter(pk=self.worker_id).update(state=WorkerState.STOPPED, current_task=None)
        self._sampler_stop.set()
        sampler.join(timeout=SAMPLE_S + 1)
        return done

    def _queue_changed(self, final: bool = False) -> None:
        """Emit `queue.changed` at most every QUEUE_EVENT_S while working, and once when the queue drains."""
        now = time.monotonic()
        if final:
            if self._last_queue_event is None:
                return
            self._last_queue_event = None
        elif self._last_queue_event is not None and now - self._last_queue_event < QUEUE_EVENT_S:
            return
        else:
            self._last_queue_event = now
        from substation.events.emit import emit

        from .summary import queue_summary

        s = queue_summary()
        emit(
            "queue.changed",
            {
                "ready_by_priority": s["ready_by_priority"],
                "running": s["running"],
                "failed": s["failed_recent"],
                "eta_seconds": s["eta_seconds"],
            },
        )

    # -- one task ----------------------------------------------------------------------------------
    def execute(self, row: Task) -> None:
        self.current = row
        Worker.objects.filter(pk=self.worker_id).update(state=WorkerState.BUSY, current_task=row)
        token = current_task_id.set(str(row.pk))
        try:
            task = load_task(row.name)
            value = task.call(*row.args, **row.kwargs)
        except Cancelled:
            Task.objects.filter(pk=row.pk).update(
                status=TaskStatus.CANCELLED,
                finished_at=timezone.now(),
                progress_note="Cancelled while running.",
            )
            log.info("Task %s cancelled while running.", row.name)
        except Interrupted as r:
            Task.objects.filter(pk=row.pk).update(
                status=TaskStatus.READY,
                run_after=timezone.now(),
                attempts=max(row.attempts - 1, 0),
                progress_note=str(r)[:300],
                worker=None,
            )
            log.info("Task %s put back in the queue: the worker is stopping.", row.name)
        except Reschedule as r:
            Task.objects.filter(pk=row.pk).update(
                status=TaskStatus.READY,
                run_after=r.run_after,
                attempts=max(row.attempts - 1, 0),
                progress_note=r.note[:300],
                worker=None,
            )
        except Exception as exc:  # noqa: BLE001
            text = "".join(traceback.format_exception(exc)) + engine_excerpt(exc)
            if row.attempts < row.max_attempts:
                Task.objects.filter(pk=row.pk).update(
                    status=TaskStatus.READY,
                    run_after=timezone.now() + backoff(row.attempts),
                    error=text,
                    worker=None,
                )
                log.warning(
                    "Task %s failed (attempt %s of %s); retrying.", row.name, row.attempts, row.max_attempts
                )
            else:
                Task.objects.filter(pk=row.pk).update(
                    status=TaskStatus.FAILED, finished_at=timezone.now(), error=text
                )
                log.error("Task %s failed after %s attempts: %s", row.name, row.attempts, exc)
                from substation.notify import send

                send(
                    "job_failed",
                    "A SubStation job failed",
                    f"{row.name.rsplit('.', 1)[-1].replace('_', ' ')}: {exc}"[:300],
                )
        else:
            Task.objects.filter(pk=row.pk).update(
                status=TaskStatus.SUCCEEDED,
                finished_at=timezone.now(),
                return_value=_jsonable(value),
                progress=1.0,
                error=None,
            )
        finally:
            current_task_id.reset(token)
            self.current = None


def _jsonable(value: object) -> object:
    from django_tasks.utils import normalize_json

    try:
        return normalize_json(value)
    except TypeError:
        return repr(value)
