# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0004_auto_20150703_1703'),
    ]

    operations = [
        migrations.AddField(
            model_name='quest',
            name='submission_details',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='quest',
            name='verification_required',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='quest',
            name='name',
            field=models.CharField(unique=True, max_length=50),
        ),
    ]
