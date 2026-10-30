"""Drop the badge assertion's old course column (#2888).

Release two of CONTRIBUTING.md's two-release drop ("Migrations and the deploy window").
0021 took `course` out of Django's state and dropped its foreign key, and has been deployed,
so no running version selects the column any more. RunSQL rather than RemoveField, since the
field is already gone from the migration state.

The reverse puts the column back empty: the stamps it held were copied onto the assertions'
registrations by 0020, whose own reverse fills it again from them.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0021_stop_using_badgeassertion_course"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "badges_badgeassertion" DROP COLUMN "course_id";',
            reverse_sql='ALTER TABLE "badges_badgeassertion" ADD COLUMN "course_id" integer NULL;',
        ),
    ]
