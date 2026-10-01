"""Regression tests for issue #2809: starting a quest on an old deck failed with
'null value in column "semester_id" ... violates not-null constraint'.

Decks that were already running when the app's migrations were started afresh in
December 2018 kept tables built from the models of that time, in which a
submission's semester, among other foreign keys, could not be empty. Migration
0056 lets every column accept NULL whose field allows it. These tests make the test
deck look like such an old deck by making those columns reject NULL, then run the
repair.
"""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()

# The migration module starts with a digit, so it can't be imported with a plain
# ``import`` statement.
migration_0056 = importlib.import_module("quest_manager.migrations.0056_drop_not_null_where_fields_allow_null")


class DropNotNullWhereFieldsAllowNullTest(ByteDeckTenantTestCase):
    """Migration 0056 brings an old deck's columns in line with the models."""

    # Foreign keys that the Django 2 upgrade of December 2018 let be empty, whose
    # columns still reject NULL on decks from before it
    COLUMNS_OLD_DECKS_REQUIRE = (
        ("quest_manager_questsubmission", "semester_id"),
        ("courses_coursestudent", "semester_id"),
        ("courses_coursestudent", "block_id"),
        ("courses_coursestudent", "course_id"),
        ("courses_coursestudent", "grade_fk_id"),
        ("comments_document", "comment_id"),
    )

    def reject_null(self, table, column):
        """Make a column of the test deck reject NULL, as it still does on a deck from before December 2018."""
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE %s ALTER COLUMN %s SET NOT NULL" % (connection.ops.quote_name(table), connection.ops.quote_name(column))
            )

    def accepts_null(self, table, column):
        """Whether a column of the test deck accepts NULL."""
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table)
        return next(info.null_ok for info in description if info.name == column)

    def repair(self):
        """Run the migration's repair the way the migration executor would."""
        with connection.schema_editor() as schema_editor:
            migration_0056.drop_not_null_where_fields_allow_null(django_apps, schema_editor)

    def test_start__a_student_in_no_semester_on_an_old_deck(self):
        """The crash in the issue. On a deck whose submissions still require a semester, a
        student registered in none can't start a quest, because their work belongs to no
        semester. After the repair, they can."""
        self.reject_null("quest_manager_questsubmission", "semester_id")
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, xp=5, published=True, archived=False, available_outside_course=True)

        with self.assertRaises(IntegrityError):
            QuestSubmission.objects.create_submission(student, quest)

        self.repair()

        submission = QuestSubmission.objects.create_submission(student, quest)
        self.assertIsNone(submission.semester)

    def test_drop_not_null_where_fields_allow_null__every_column_old_decks_require(self):
        """Each foreign key the 2018 upgrade let be empty accepts NULL again, in every app, and
        a column whose field is required keeps rejecting it."""
        for table, column in self.COLUMNS_OLD_DECKS_REQUIRE:
            self.reject_null(table, column)

        self.repair()

        for table, column in self.COLUMNS_OLD_DECKS_REQUIRE:
            with self.subTest(column=f"{table}.{column}"):
                self.assertTrue(self.accepts_null(table, column))
        self.assertFalse(self.accepts_null("quest_manager_questsubmission", "user_id"))

    def test_drop_not_null_where_fields_allow_null__changes_nothing_on_a_deck_built_by_the_migrations(self):
        """On a deck whose tables were built by the migrations, every column already agrees
        with its field, so the repair alters nothing."""
        with CaptureQueriesContext(connection) as queries:
            self.repair()

        self.assertEqual([query["sql"] for query in queries if query["sql"].startswith("ALTER TABLE")], [])
