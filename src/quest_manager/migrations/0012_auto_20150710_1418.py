# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0011_auto_20150710_0808'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='prerequisite',
            name='alternate_prerequisite_item',
        ),
        migrations.RemoveField(
            model_name='prerequisite',
            name='maximum_XP',
        ),
        migrations.RemoveField(
            model_name='prerequisite',
            name='minimum_XP',
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='alternate_prerequisite_item_1',
            field=models.ForeignKey(blank=True, related_name='alternate_prerequisite_item_1', help_text='user must have one of the prerequisite items', null=True, to='quest_manager.Quest'),
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='alternate_prerequisite_item_2',
            field=models.ForeignKey(blank=True, related_name='alternate_prerequisite_item_2', help_text='user must have one of the prerequisite items', null=True, to='quest_manager.Quest'),
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='invert_alt_prerequisite_1',
            field=models.BooleanField(help_text='item is available if user does NOT have this pre-requisite', default=False),
        ),
        migrations.AddField(
            model_name='prerequisite',
            name='invert_alt_prerequisite_2',
            field=models.BooleanField(help_text='item is available if user does NOT have this pre-requisite', default=False),
        ),
        migrations.AddField(
            model_name='quest',
            name='maximum_XP',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quest',
            name='minimum_XP',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='prerequisite',
            name='invert_prerequisite',
            field=models.BooleanField(help_text='item is available if user does NOT have this pre-requisite', default=False),
        ),
    ]
