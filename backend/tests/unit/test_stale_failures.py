"""A failure that no longer matters clears itself (2026-10-15): a later successful run of the same job, or a master
built or deleted since."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalogue.models import Dataset
from apps.processing.models import Master
from substation.tasks.models import Task, TaskStatus
from substation.tasks.summary import open_failures

pytestmark = pytest.mark.django_db


def _task(name, args, status, minutes_ago):
    t = timezone.now() - timedelta(minutes=minutes_ago)
    return Task.objects.create(
        name=name, args=args, status=status, run_after=t, enqueued_at=t, finished_at=t, max_attempts=1
    )


def test_failures_that_were_resolved_drop_off():
    ds = Dataset.objects.create(group_key="m", target="M 42", filter_norm="L", display_name="M 42 · L")
    built = Master.objects.create(dataset=ds, version=2, state="current")
    broken = Master.objects.create(dataset=ds, version=3, state="failed")
    retried = _task("apps.ingest.tasks.hash.hash_file", [1, "a.fits"], TaskStatus.FAILED, 30)
    _task("apps.ingest.tasks.hash.hash_file", [1, "a.fits"], TaskStatus.SUCCEEDED, 10)
    gone = _task("apps.processing.masters.integrate", [9999], TaskStatus.FAILED, 20)
    since_built = _task("apps.processing.masters.integrate", [built.pk], TaskStatus.FAILED, 20)
    real = _task("apps.processing.masters.integrate", [broken.pk], TaskStatus.FAILED, 5)
    left = {t.pk for t in open_failures()}
    assert real.pk in left and not left & {retried.pk, gone.pk, since_built.pk}
