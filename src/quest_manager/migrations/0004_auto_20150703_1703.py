# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0003_auto_20150703_1653'),
    ]

    operations = [
        migrations.CreateModel(
            name='Quest',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('name', models.CharField(unique=True, max_length=100)),
                ('datetime_created', models.DateTimeField(auto_now_add=True)),
                ('datetime_last_edit', models.DateTimeField(auto_now=True)),
                ('short_description', models.TextField(max_length=250, blank=True)),
                ('xp', models.PositiveIntegerField(blank=True, default=0)),
                ('visible', models.BooleanField(default=True)),
                ('max_repeats', models.IntegerField(blank=True, default=0, help_text='0 = not repeatable, -1 = unlimited')),
                ('hours_between_repeats', models.PositiveIntegerField(blank=True, default=0)),
                ('date_available', models.DateField(blank=True, null=True)),
                ('time_available', models.TimeField(blank=True, null=True)),
                ('date_expired', models.DateField(blank=True, null=True)),
                ('time_expired', models.TimeField(blank=True, null=True)),
                ('instructions', models.TextField(blank=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.DeleteModel(
            name='XPItem',
        ),
    ]
