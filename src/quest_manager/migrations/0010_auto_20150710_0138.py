# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0009_auto_20150710_0013'),
    ]

    operations = [
        migrations.CreateModel(
            name='Prerequisite',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, serialize=False, auto_created=True)),
                ('NOT_prereq_item', models.BooleanField(default=False)),
                ('minimum_XP', models.PositiveIntegerField(null=True, blank=True)),
                ('maximum_XP', models.PositiveIntegerField(null=True, blank=True)),
                ('parent_quest', models.ForeignKey(to='quest_manager.Quest')),
                ('prerequisite_item', models.ForeignKey(to='quest_manager.Quest', related_name='Quest_Prereq')),
            ],
        ),
        migrations.AlterModelOptions(
            name='category',
            options={'verbose_name_plural': 'Categories'},
        ),
    ]
