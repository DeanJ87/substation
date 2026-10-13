"""ingest.tidy_bin (spec 011): once a day, bin lights rejected for longer than the waiting period, then delete
binned files whose purge date has passed."""

from __future__ import annotations

from django.utils import timezone

from apps.catalogue.services.binning import auto_bin, purge_due
from substation.tasks import PRIORITY_BULK, station_task


@station_task(queue_name="ingest", priority=PRIORITY_BULK + 5, max_attempts=2)
def tidy_bin() -> dict:
    from apps.libraries.models import InstallationSettings

    binned = auto_bin()
    purged = purge_due()
    s = InstallationSettings.load()
    p = dict(s.processing or {})
    p["bin_tidied_on"] = timezone.localdate().isoformat()
    InstallationSettings.objects.filter(pk=s.pk).update(processing=p)
    return {**binned, **purged}
