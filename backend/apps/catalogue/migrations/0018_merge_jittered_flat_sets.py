"""002-DR-24: flats of one filter and session whose exposures differ by NINA's flat-wizard jitter (0.00654 / 0.00655 s)
were split into separate sets. Merge them: within one camera, filter, gain, offset and binning, a set starting within
two hours of the previous one's end, with an exposure within 5% of it, joins it. Built masters move with their frames
(their history is kept); the merged set is rebuilt by the automatic builds when it next grows, or by hand."""

from datetime import timedelta

from django.db import migrations

GAP = timedelta(hours=2)
TOLERANCE = 0.05


def merge(apps, schema_editor):  # noqa: ANN001, ARG001
    CalibrationSet = apps.get_model("catalogue", "CalibrationSet")
    Frame = apps.get_model("catalogue", "Frame")
    BuiltMaster = apps.get_model("processing", "BuiltMaster")
    groups: dict[tuple, list] = {}
    for cs in CalibrationSet.objects.filter(type="flat").order_by("session_start_utc"):
        key = (cs.camera, cs.filter_norm, cs.gain, cs.offset, cs.xbin, cs.ybin)
        groups.setdefault(key, []).append(cs)
    for sets in groups.values():
        current = None
        for cs in sets:
            close = (
                current is not None
                and cs.session_start_utc - current.session_end_utc <= GAP
                and abs(cs.exptime_s - current.exptime_s) <= TOLERANCE * current.exptime_s
            )
            if not close:
                current = cs
                continue
            Frame.objects.filter(calibration_set=cs).update(calibration_set=current)
            BuiltMaster.objects.filter(calibration_set=cs).update(calibration_set=current)
            current.session_start_utc = min(current.session_start_utc, cs.session_start_utc)
            current.session_end_utc = max(current.session_end_utc, cs.session_end_utc)
            current.frame_count = Frame.objects.filter(calibration_set=current, status="catalogued").count()
            current.save(update_fields=["session_start_utc", "session_end_utc", "frame_count"])
            cs.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0017_frame_binned_dataset"),
        ("processing", "0013_regional_top_is_top"),
    ]
    operations = [migrations.RunPython(merge, migrations.RunPython.noop)]
