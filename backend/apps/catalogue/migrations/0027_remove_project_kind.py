# The kind now lives in kind_override (the owner's choice) or is worked out; the old column goes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0026_projects_by_season'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='kind',
            field=models.CharField(choices=[('single', 'Single field'), ('mosaic', 'Mosaic')], default='single', max_length=10),
        ),
    ]
