# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0008_auto_20150710_0011'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quest',
            name='date_available',
            field=models.DateField(default=django.utils.timezone.now),
        ),
    ]
