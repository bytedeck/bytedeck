# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0006_auto_20150705_1140'),
    ]

    operations = [
        migrations.AddField(
            model_name='quest',
            name='category',
            field=models.CharField(max_length=250, default=''),
        ),
    ]
