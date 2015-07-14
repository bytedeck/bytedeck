# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0007_quest_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(primary_key=True, auto_created=True, verbose_name='ID', serialize=False)),
                ('category', models.CharField(unique=True, max_length=50)),
            ],
        ),
        migrations.AlterField(
            model_name='quest',
            name='category',
            field=models.ForeignKey(to='quest_manager.Category'),
        ),
        migrations.AlterField(
            model_name='quest',
            name='date_available',
            field=models.DateField(default=datetime.date(2015, 7, 10)),
        ),
        migrations.AlterField(
            model_name='quest',
            name='time_available',
            field=models.TimeField(default=datetime.time(0, 0)),
        ),
    ]
