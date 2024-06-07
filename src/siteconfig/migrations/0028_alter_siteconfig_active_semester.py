# Generated by Django 3.2.25 on 2024-06-07 17:19

from django.db import migrations, models
import django.db.models.deletion
import siteconfig.models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0028_semester_name'),
        ('siteconfig', '0027_siteconfig_show_all_tags_on_profiles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='active_semester',
            field=models.ForeignKey(default=siteconfig.models.get_active_semester, help_text='Your currently active semester.  New semesters can be created from the admin menu.', null=True, on_delete=django.db.models.deletion.PROTECT, to='courses.semester', verbose_name='Active Semester'),
        ),
    ]
