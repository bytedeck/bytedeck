# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0010_auto_20150710_0138'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='prerequisite',
            name='NOT_prereq_item',
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='alternate_prerequisite_item',
            field=models.ForeignKey(related_name='alternate_prerequisite_item', blank=True, help_text='user must have one or the other item', null=True, to='quest_manager.Quest'),
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='invert_prerequisite',
            field=models.BooleanField(help_text='item is available if user does NOT have the pre-requisite', default=False),
        ),
        migrations.AlterField(
            model_name='prerequisite',
            name='prerequisite_item',
            field=models.ForeignKey(related_name='prerequisite_item', to='quest_manager.Quest'),
        ),
    ]
