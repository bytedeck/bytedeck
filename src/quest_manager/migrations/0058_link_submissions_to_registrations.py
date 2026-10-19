"""Link each submission to the course registration its course stamp points at (#2875).

A submission said which of the student's courses its XP counts toward by naming the course.
It now names the registration instead, so the work stays with that registration when a
teacher changes its course. This copies the existing stamps across: a submission stamped with
a course is linked to the registration holding that course for the same student in the same
semester. One that no registration matches (its course has since been changed or removed, or
it belongs to no semester) is left unlinked, which is how it already counts: shared evenly
between the student's courses.

The copy is SQL rather than the ORM because the model no longer has the course field (the
next migration takes it out of Django's state), and the tests run it the same way.
"""
from django.db import migrations

#: Should a student hold the same course twice in one semester, the older registration is
#: taken, so the result does not depend on the order rows come back in. Unqualified table
#: names are right here: migrate_schemas runs this once per deck with that deck's schema on
#: the search path.
LINK_SQL = """
UPDATE quest_manager_questsubmission AS submission
SET registration_id = (
    SELECT registration.id
    FROM courses_coursestudent AS registration
    WHERE registration.user_id = submission.user_id
      AND registration.semester_id = submission.semester_id
      AND registration.course_id = submission.course_id
    ORDER BY registration.id
    LIMIT 1
)
WHERE submission.course_id IS NOT NULL;
"""

#: The reverse, for development: stamp each linked submission with its registration's course.
UNLINK_SQL = """
UPDATE quest_manager_questsubmission AS submission
SET course_id = registration.course_id
FROM courses_coursestudent AS registration
WHERE registration.id = submission.registration_id;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("quest_manager", "0057_questsubmission_registration"),
    ]

    operations = [
        migrations.RunSQL(LINK_SQL, reverse_sql=UNLINK_SQL),
    ]
