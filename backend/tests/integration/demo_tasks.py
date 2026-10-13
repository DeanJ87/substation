"""Tasks used only by the queue tests."""

import os
import time

from substation.tasks import Reschedule, report_progress, station_task


@station_task(queue_name="default")
def record(label: str) -> str:
    from substation.events.emit import emit

    emit("test.ran", {"label": label, "pid": os.getpid()})
    return label


@station_task(queue_name="default", max_attempts=3)
def flaky(label: str, fail_times: int) -> str:
    from substation.events.models import Event

    seen = Event.objects.filter(type="test.flaky", payload__label=label).count()
    Event.objects.create(type="test.flaky", payload={"label": label})
    if seen < fail_times:
        raise RuntimeError(f"failure {seen + 1}")
    return "ok"


@station_task(queue_name="default")
def reschedule_once(label: str) -> str:
    from substation.events.models import Event

    if not Event.objects.filter(type="test.resched", payload__label=label).exists():
        Event.objects.create(type="test.resched", payload={"label": label})
        raise Reschedule(0.0, "file still being written")
    return "done"


@station_task(queue_name="default")
def slow(label: str, seconds: float) -> str:
    for i in range(int(seconds * 10)):
        report_progress(i / (seconds * 10), "working")
        time.sleep(0.1)
    from substation.events.emit import emit

    emit("test.ran", {"label": label, "pid": os.getpid()})
    return label


@station_task(queue_name="default", slot="siril_heavy")
def heavy(label: str, seconds: float) -> str:
    time.sleep(seconds)
    return label


@station_task(queue_name="default", max_attempts=3)
def asks_to_stop(label: str) -> str:
    """Asks for its own cancellation, as Activity's Cancel would, then reports progress."""
    from substation.tasks import current_task_id
    from substation.tasks.models import Task

    Task.objects.filter(pk=str(current_task_id.get())).update(cancel_requested=True)
    report_progress(0.5, "half way")
    return "finished anyway"
