# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='XPItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('datetime_created', models.DateTimeField(auto_now_add=True)),
                ('datetime_last_edit', models.DateTimeField(auto_now_add=True)),
                ('short_description', models.CharField(max_length=250, blank=True, null=True)),
                ('visible', models.BooleanField(default=True)),
                ('repeatable_days', models.PositiveSmallIntegerField(default=0)),
                ('max_repeats', models.PositiveSmallIntegerField(default=0)),
                ('date_available', models.DateField()),
                ('time_available', models.TimeField()),
                ('date_expired', models.DateField()),
                ('time_expired', models.TimeField()),
            ],
        ),
    ]
