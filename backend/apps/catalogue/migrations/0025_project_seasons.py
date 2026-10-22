# Projects by season (006-DR-20 amendment 2026-10-22): a season and an optional own name, the kind worked out unless
# the owner chose one, done, and a flag for projects held apart when seasons were joined.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0024_collection_moves'),
    ]

    operations = [
        migrations.RenameField(model_name='project', old_name='name', new_name='own_name'),
        migrations.AlterField(
            model_name='project',
            name='own_name',
            field=models.CharField(blank=True, default='', help_text='optional, after the season', max_length=200),
        ),
        migrations.AddField(
            model_name='project',
            name='season',
            field=models.CharField(blank=True, default='', help_text='"2026", or "2025–26" over New Year', max_length=20),
        ),
        migrations.AddField(
            model_name='project',
            name='kind_override',
            field=models.CharField(blank=True, choices=[('single', 'Single field'), ('mosaic', 'Mosaic')], help_text="the owner's choice; empty = automatic", max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='done_at',
            field=models.DateTimeField(blank=True, help_text='the owner finished shooting it', null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='needs_review',
            field=models.BooleanField(default=False, help_text='held apart when seasons were joined; the owner decides'),
        ),
        migrations.AddField(
            model_name='project',
            name='review_reason',
            field=models.CharField(blank=True, default='', max_length=300),
        ),
        migrations.AlterField(
            model_name='change',
            name='kind',
            field=models.CharField(choices=[('verdict', 'Verdict'), ('agree', 'Agree'), ('bin', 'Bin'), ('move', 'Move'), ('dismiss', 'Dismiss'), ('qa', 'Qa'), ('archive', 'Archive'), ('project', 'Project')], max_length=10),
        ),
    ]
