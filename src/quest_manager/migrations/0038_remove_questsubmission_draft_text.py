# Generated by Django 3.2.25 on 2025-02-08 19:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quest_manager', '0037_alter_questsubmission_draft_comment'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='questsubmission',
            name='draft_text',
        ),
    ]
