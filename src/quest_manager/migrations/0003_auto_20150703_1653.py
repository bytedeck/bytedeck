# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0002_auto_20150703_1646'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='xpitem',
            name='repeatable',
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='hours_between_repeats',
            field=models.PositiveIntegerField(blank=True, default=0),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='max_repeats',
            field=models.IntegerField(help_text='0 = not repeatable, -1 = unlimited', blank=True, default=0),
        ),
        migrations.AlterField(
            model_name='xpitem',
            name='short_description',
            field=models.CharField(max_length=250, null=True),
        ),
    ]
