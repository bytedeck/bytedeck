# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0012_auto_20150710_1418'),
    ]

    operations = [
        migrations.AddField(
            model_name='quest',
            name='icon',
            field=models.ImageField(null=True, upload_to='icons'),
        ),
    ]
