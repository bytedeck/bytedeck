# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='xpitem',
            name='repeatable_days',
        ),
        migrations.AddField(
            model_name='xpitem',
            name='hours_between_repeats',
            field=models.PositiveSmallIntegerField(default=0, help_text='Blah BLah BLah'),
        ),
        migrations.AddField(
            model_name='xpitem',
            name='repeatable',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='date_available',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='date_expired',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='time_available',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='time_expired',
            field=models.TimeField(null=True, blank=True),
        ),
    ]
