# Generated by Django 3.2.14 on 2022-07-22 01:55

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0027_alter_quest_options'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CommonData',
            new_name='CommonQuestInfo',
        ),
    ]
