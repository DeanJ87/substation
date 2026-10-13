"""Masters' "across the field" zones had top and bottom swapped (Siril's y runs from the top); swap the stored
ones and rewrite their tilt notes (2026-10-12)."""

from django.db import migrations

SWAP = {"top_left": "bottom_left", "top_right": "bottom_right", "bottom_left": "top_left", "bottom_right": "top_right"}


def swap(apps, schema_editor):
    from apps.engine.parse import tilt_note

    Master = apps.get_model("processing", "Master")
    for m in Master.objects.exclude(report={}):
        reg = (m.report or {}).get("regional") or {}
        zones = reg.get("zones")
        if not zones:
            continue
        fixed = {SWAP.get(k, k): v for k, v in zones.items()}
        report = dict(m.report)
        report["regional"] = {**reg, "zones": fixed, "tilt_note": tilt_note(fixed)}
        Master.objects.filter(pk=m.pk).update(report=report)


class Migration(migrations.Migration):
    dependencies = [("processing", "0012_resolve_misread_fields")]
    operations = [migrations.RunPython(swap, swap)]  # swapping twice restores it
