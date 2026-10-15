"""Spec 019 amendment (2026-10-15): goals belong to a project (one way of shooting a target), not the collection.
A collection's goals move to its newest project (by its latest night); one with no project keeps none."""

from django.db import migrations, models
from django.db.models import Max


def move_goals(apps, schema_editor):
    Collection = apps.get_model("catalogue", "Collection")
    Project = apps.get_model("catalogue", "Project")
    for col in Collection.objects.exclude(goals={}):
        newest = (
            Project.objects.filter(collection=col)
            .annotate(last=Max("datasets__nights__night__date"))
            .order_by("-last", "-pk")
            .first()
        )
        if newest is not None:
            newest.goals = col.goals
            newest.save(update_fields=["goals"])


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0021_collection_goals")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="goals",
            field=models.JSONField(blank=True, default=dict, help_text="hours of usable integration wanted, per filter"),
        ),
        migrations.RunPython(move_goals, migrations.RunPython.noop),
        migrations.RemoveField(model_name="collection", name="goals"),
    ]
