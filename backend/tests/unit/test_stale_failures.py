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


def test_a_version_replaced_by_a_later_one_or_deleted_drops_off():
    """M 42 L, 2026-10-15: v1 and v2 failed, v4 was built; v3 was deleted and its post-processing had failed."""
    ds = Dataset.objects.create(group_key="m42", target="M 42", filter_norm="L", display_name="M 42 · L")
    v1 = Master.objects.create(dataset=ds, version=1, state="failed")
    v3 = Master.objects.create(dataset=ds, version=3, state="deleted")
    Master.objects.create(dataset=ds, version=4, state="current")
    old = _task("apps.processing.masters.integrate", [v1.pk], TaskStatus.FAILED, 30)
    post = _task("apps.processing.postprocess.postprocess_master", [v3.pk], TaskStatus.FAILED, 20)
    left = {t.pk for t in open_failures()}
    assert not left & {old.pk, post.pk}


def test_a_calibration_build_that_was_rebuilt_or_emptied_drops_off():
    from apps.catalogue.models import CalibrationSet
    from apps.processing.models import BuiltMaster

    now = timezone.now()
    emptied = CalibrationSet.objects.create(
        type="flat", camera="c", filter_norm="Ha2", exptime_s=1, session_start_utc=now, session_end_utc=now
    )
    failed = BuiltMaster.objects.create(calibration_set=emptied, state="failed")
    t = _task("apps.processing.calibration.build_master", [failed.pk], TaskStatus.FAILED, 10)
    assert t.pk not in {x.pk for x in open_failures()}
