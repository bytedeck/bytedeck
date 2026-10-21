"""Tests for the data migrations that link students' work to their course registrations (#2875).

Submissions and badge assertions used to say which course their XP counts toward by naming the
course. They now name the registration, and quest_manager 0058 and badges 0020 copy the old
stamps across. The models no longer have the course field, and quest_manager 0060 and badges
0022 drop its column (#2888), so each test puts the column back with those migrations' own
reverse SQL, and its transaction takes the column away again. The tests stamp the column with
SQL and run each migration's own SQL, the same as migrate_schemas does.
"""
from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import connection

from model_bakery import baker

from badges.models import Badge, BadgeAssertion
from courses.models import Block, Course, CourseStudent, Grade, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()
link_submissions = import_module("quest_manager.migrations.0058_link_submissions_to_registrations")
link_assertions = import_module("badges.migrations.0020_link_assertions_to_registrations")
drop_submission_column = import_module("quest_manager.migrations.0060_drop_questsubmission_course_column")
drop_assertion_column = import_module("badges.migrations.0022_drop_badgeassertion_course_column")


class LinkWorkToRegistrationsMigrationTest(ByteDeckTenantTestCase):
    """The data migrations that link submissions and badge assertions to registrations."""

    def setUp(self):
        """The old course columns, and a student in two courses this semester."""
        for drop in (drop_submission_column, drop_assertion_column):
            self._run(drop.Migration.operations[0].reverse_sql)
        self.semester = SiteConfig.get().active_semester
        self.student = baker.make(User)
        self.maths = baker.make(Course, title='Maths')
        self.maths_registration = self._register(self.maths)
        self.art_registration = self._register(baker.make(Course, title='Art'))

    def _register(self, course, semester=None, grade=None):
        """Register the student in `course` and return the registration.

        Args:
            course (Course): the course to register them in.
            semester (Semester): defaults to the deck's active semester.
            grade (Grade): defaults to none.

        Returns:
            CourseStudent: the new registration.
        """
        return baker.make(
            CourseStudent, user=self.student, course=course, block=baker.make(Block),
            semester=semester or self.semester, grade_fk=grade,
        )

    def _submission_stamped_with(self, course, semester=None):
        """Make a submission whose old course column names `course`, linked to no registration.

        Args:
            course (Course | None): the course in the old column.
            semester (Semester): defaults to the deck's active semester.

        Returns:
            QuestSubmission: the submission.
        """
        submission = baker.make(QuestSubmission, user=self.student, quest=baker.make(Quest), semester=semester or self.semester)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE quest_manager_questsubmission SET course_id = %s, registration_id = NULL WHERE id = %s",
                [course.pk if course else None, submission.pk],
            )
        return submission

    def _run(self, sql):
        """Run a migration's SQL in this test's deck.

        Args:
            sql (str): the statement to run.
        """
        with connection.cursor() as cursor:
            cursor.execute(sql)

    def test_link_submissions__links_work_to_the_registration_holding_its_course(self):
        """A submission stamped with a course is linked to the student's registration in that
        course this semester, so it keeps counting toward the same course."""
        submission = self._submission_stamped_with(self.maths)

        self._run(link_submissions.LINK_SQL)

        submission.refresh_from_db()
        self.assertEqual(submission.registration, self.maths_registration)

    def test_link_submissions__leaves_work_no_registration_matches_unlinked(self):
        """Work stamped with a course the student no longer holds that semester, or with none at
        all, stays unlinked, so it is shared between their courses as it already was."""
        dropped = self._submission_stamped_with(baker.make(Course, title='Dropped'))
        last_term = self._submission_stamped_with(
            self.maths, semester=baker.make(Semester, status=Semester.Status.ARCHIVED),
        )
        unassigned = self._submission_stamped_with(None)

        self._run(link_submissions.LINK_SQL)

        for submission in (dropped, last_term, unassigned):
            submission.refresh_from_db()
            self.assertIsNone(submission.registration)

    def test_link_submissions__takes_the_older_of_two_registrations_in_the_same_course(self):
        """A student holding one course twice in a semester has their work linked to the older
        registration, so the result does not depend on the order the database returns rows."""
        self._register(self.maths, grade=baker.make(Grade))
        submission = self._submission_stamped_with(self.maths)

        self._run(link_submissions.LINK_SQL)

        submission.refresh_from_db()
        self.assertEqual(submission.registration, self.maths_registration)

    def test_link_submissions__reverses_by_stamping_the_registrations_course(self):
        """Unapplying the migration stamps each linked submission with its registration's course
        again, which is what the model before it reads."""
        submission = baker.make(
            QuestSubmission, user=self.student, quest=baker.make(Quest), semester=self.semester,
            registration=self.art_registration,
        )

        self._run(link_submissions.UNLINK_SQL)

        with connection.cursor() as cursor:
            cursor.execute("SELECT course_id FROM quest_manager_questsubmission WHERE id = %s", [submission.pk])
            self.assertEqual(cursor.fetchone()[0], self.art_registration.course_id)

    def test_link_assertions__links_a_badge_to_the_registration_holding_its_course(self):
        """A badge stamped with a course is linked the same way, and one with none stays
        unlinked; unapplying stamps the linked one's course back."""
        stamped, unstamped = (
            baker.make(BadgeAssertion, user=self.student, badge=baker.make(Badge), semester=self.semester)
            for _ in range(2)
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE badges_badgeassertion SET course_id = %s, registration_id = NULL WHERE id = %s",
                [self.maths.pk, stamped.pk],
            )

        self._run(link_assertions.LINK_SQL)

        stamped.refresh_from_db()
        unstamped.refresh_from_db()
        self.assertEqual(stamped.registration, self.maths_registration)
        self.assertIsNone(unstamped.registration)

        with connection.cursor() as cursor:
            cursor.execute("UPDATE badges_badgeassertion SET course_id = NULL WHERE id = %s", [stamped.pk])
        self._run(link_assertions.UNLINK_SQL)
        with connection.cursor() as cursor:
            cursor.execute("SELECT course_id FROM badges_badgeassertion WHERE id = %s", [stamped.pk])
            self.assertEqual(cursor.fetchone()[0], self.maths.pk)


class DropCourseColumnsMigrationTest(ByteDeckTenantTestCase):
    """quest_manager 0060 and badges 0022 drop the course columns 0059 and 0021 left behind (#2888)."""

    def test_drop_course_columns__leaves_neither_table_a_course_column(self):
        """A deck migrated to the latest migrations has no course_id column on submissions or on
        badge assertions."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND column_name = 'course_id' "
                "AND table_name IN ('quest_manager_questsubmission', 'badges_badgeassertion')"
            )
            self.assertEqual(cursor.fetchall(), [])
