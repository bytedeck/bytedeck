# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0005_auto_20150703_1710'),
    ]

    operations = [
        migrations.RenameField(
            model_name='quest',
            old_name='visible',
            new_name='visible_to_students',
        ),
    ]
