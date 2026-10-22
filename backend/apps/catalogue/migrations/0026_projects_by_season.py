"""Projects by season (006-DR-20 amendment 2026-10-22). Every project keeps its kind as the owner's choice; each gets
its season from its nights; names the old suggester gave ("2-panel mosaic 2026", "Single field 2026 · rig") give way
to the season. Then a collection's projects of one season are merged into the one with the most integration, with
the same merge the page uses, each recorded as a Change so it can be undone. A season's projects are held apart
(flagged for the owner, with the reason) when merging would lose or change something: an absorbed project is linked
to a finished image, goals differ for a filter, two of them were named by hand, or they're mosaics of different
sizes. Projects with no nights have no season and are left alone."""

import logging

from django.conf import settings
from django.db import migrations

log = logging.getLogger(__name__)


def hold_reasons(apps, group, target):
    from apps.catalogue.services.projects import _links, finished_names, goal_conflicts

    out = []
    links = _links(apps, [p.pk for p in group if p.pk != target.pk])
    linked = [fp for ids in links.values() for fp in ids]
    if linked:
        out.append(f"Linked to a finished image ({', '.join(finished_names(apps, linked))})")
    conflicts = goal_conflicts([p.goals for p in group])
    if conflicts:
        out.append("Goals differ: " + "; ".join(conflicts))
    named = [p.own_name for p in group if p.own_name]
    if len(named) > 1:
        out.append("Named by hand: " + ", ".join(named))
    sizes = {p.planned_panels for p in group if p.kind_override == "mosaic"}
    if len([p for p in group if p.kind_override == "mosaic"]) > 1 and len(sizes) > 1:
        out.append("Mosaics of " + " and ".join(str(n or "?") for n in sorted(sizes, key=lambda n: n or 0)) + " panels")
    return out


def forward(apps, schema_editor):
    from apps.catalogue.services.projects import Seasons, is_suggested_name, merge

    project = apps.get_model("catalogue", "Project")
    dataset = apps.get_model("catalogue", "Dataset")
    user_model = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    user = user_model.objects.filter(is_superuser=True).order_by("pk").first()
    for p in project.objects.all():
        p.kind_override = p.kind
        p.save(update_fields=["kind_override"])
    for col_id in sorted(set(project.objects.values_list("collection_id", flat=True))):
        seasons = Seasons(col_id, apps)
        groups = {}
        for p in project.objects.filter(collection_id=col_id).order_by("position", "pk"):
            p.season = seasons.of(dataset.objects.filter(project_id=p.pk).values_list("pk", flat=True))
            if p.season and is_suggested_name(p.own_name):
                p.own_name = ""
            p.save(update_fields=["season", "own_name"])
            if p.season:
                groups.setdefault(p.season, []).append(p)
        for season, group in groups.items():
            if len(group) < 2:
                continue
            integ = {
                p.pk: sum(dataset.objects.filter(project_id=p.pk).values_list("accepted_integration_s", flat=True))
                for p in group
            }
            target = max(group, key=lambda p: (integ[p.pk], -p.position, -p.pk))
            reasons = hold_reasons(apps, group, target)
            if reasons:
                why = "; ".join(reasons)[:300]
                log.warning("Collection %s, season %s: projects held apart: %s", col_id, season, why)
                project.objects.filter(pk__in=[p.pk for p in group]).update(needs_review=True, review_reason=why)
                continue
            merge(target.pk, [p.pk for p in group if p.pk != target.pk], user, apps=apps)


def backward(apps, schema_editor):
    from apps.catalogue.services.projects import label

    project = apps.get_model("catalogue", "Project")
    for p in project.objects.all():
        p.kind = p.kind_override or "single"
        p.own_name = label(p.season, p.own_name)
        p.save(update_fields=["kind", "own_name"])


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0025_project_seasons'),
        ('finished', '0003_remove_finishedproject_processing_and_more'),
        ('processing', '0016_sky_position'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
