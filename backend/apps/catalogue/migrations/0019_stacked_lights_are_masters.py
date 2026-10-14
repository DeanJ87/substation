"""A Seestar writes its running stack (Stacked_153_….fit, STACKCNT 153, IMAGETYP Light) beside its subs; those were
catalogued as subs and went into stacks. Re-read the targets that hold one, so the new rule moves them out of their
datasets (the worker does it; nothing to do on an empty database)."""

from django.db import migrations


def requeue(apps, schema_editor):  # noqa: ANN001, ARG001
    HeaderSnapshot = apps.get_model("catalogue", "HeaderSnapshot")
    names = set()
    for key in ("STACKCNT", "NCOMBINE"):
        for h in HeaderSnapshot.objects.filter(frame__frame_type="light", keywords__has_key=key).select_related(
            "frame"
        ):
            v = h.keywords.get(key)
            v = v.get("value") if isinstance(v, dict) else v
            try:
                many = v is not None and int(float(v)) > 1
            except (TypeError, ValueError):
                many = False
            if many and h.frame.target:
                names.add(h.frame.target)
    if names:
        from apps.ingest.tasks.reresolve import reresolve_targets
        from substation.tasks import enqueue

        enqueue(reresolve_targets, sorted(names), dedupe_key="stacked-lights")


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0018_merge_jittered_flat_sets")]
    operations = [migrations.RunPython(requeue, migrations.RunPython.noop)]
