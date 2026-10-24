# 004-DR-32: a combined master says how it was made: stitched as a mosaic, or stacked together.

from django.db import migrations, models


def mark_mosaics(apps, schema_editor):
    """A combined master made by placing panels on a mosaic canvas said so ("Mosaic of n panel(s)."): stitched."""
    cm = apps.get_model("processing", "CombinedMaster")
    cm.objects.filter(state_reason__startswith="Mosaic of").update(method="stitch")


class Migration(migrations.Migration):
    dependencies = [
        ("processing", "0016_sky_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="combinedmaster",
            name="method",
            field=models.CharField(
                choices=[("stitch", "Stitch mosaic"), ("stack", "Stack together")], default="stack", max_length=8
            ),
        ),
        migrations.RunPython(mark_mosaics, migrations.RunPython.noop),
    ]
