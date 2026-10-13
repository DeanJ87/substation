"""Fields under a degree were read as degrees ("26m 55.59s" → 26.9°, 2026-10-12). Drop those solves so the solve
backfill makes them again with the fixed reading; nothing else depends on a stored solve."""

from django.db import migrations
from django.db.models import F


def drop_misread(apps, schema_editor):
    PlateSolve = apps.get_model("processing", "PlateSolve")
    # no camera is 20,000 pixels wide: a field that wide at the solved scale was misread
    PlateSolve.objects.filter(state="solved", scale_arcsec__gt=0).annotate(
        px=F("fov_w_deg") * 3600 / F("scale_arcsec")
    ).filter(px__gt=20000).delete()


class Migration(migrations.Migration):
    dependencies = [("processing", "0011_master_solve")]
    operations = [migrations.RunPython(drop_misread, migrations.RunPython.noop)]
