"""Drop the submission's old course column (#2888).

Release two of CONTRIBUTING.md's two-release drop ("Migrations and the deploy window").
0059 took `course` out of Django's state and dropped its foreign key, and has been deployed,
so no running version selects the column any more. RunSQL rather than RemoveField, since the
field is already gone from the migration state.

The reverse puts the column back empty: the stamps it held were copied onto the submissions'
registrations by 0058, whose own reverse fills it again from them.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quest_manager", "0059_stop_using_questsubmission_course"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "quest_manager_questsubmission" DROP COLUMN "course_id";',
            reverse_sql='ALTER TABLE "quest_manager_questsubmission" ADD COLUMN "course_id" integer NULL;',
        ),
    ]
