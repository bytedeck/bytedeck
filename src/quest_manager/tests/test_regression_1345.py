"""Regression tests for issue #1345 -- "Quests are at times repeatable when
they shouldn't be".

A concurrent "double start" (a student opening two browser tabs and starting the
same non-repeatable quest before either submission is committed) could create two
in-progress submissions of the same quest. Both could then be completed and
approved, granting XP twice.

The fix is a partial unique constraint forbidding more than one *in-progress*
(``is_completed=False``) submission per ``(user, quest, semester)``, plus
``create_submission()`` catching the resulting ``IntegrityError`` and returning
the submission that won the race instead of a duplicate.
"""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()

# The migration module starts with a digit, so it can't be imported with a
# plain ``import`` statement.
migration_0049 = importlib.import_module(
    "quest_manager.migrations.0049_inprogress_submission_unique_constraint"
)


class DoubleStartRaceTest(TenantTestCase):
    """The concurrent-double-start vector from issue #1345."""

    def setUp(self):
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(
            Quest, name="One-time quest", xp=10,
            max_repeats=0, repeat_per_semester=False,
            published=True, archived=False,
        )
        self.active_semester = SiteConfig.get().active_semester

    def _in_progress_count(self):
        return QuestSubmission.objects.filter(
            quest=self.quest, user=self.student, is_completed=False,
        ).count()

    def test_unique_constraint_forbids_second_in_progress_submission(self):
        """Saving a second in-progress submission of the same quest/semester
        raises IntegrityError (the DB-level guard)."""
        QuestSubmission.objects.create_submission(self.student, self.quest)

        duplicate = QuestSubmission(
            quest=self.quest, user=self.student, ordinal=2,
            semester_id=self.active_semester.pk,
        )
        with self.assertRaises(IntegrityError):
            # Wrapped so the failed statement doesn't poison the test transaction.
            with transaction.atomic():
                duplicate.save()

    def test_create_submission_twice_returns_existing_and_makes_no_duplicate(self):
        """Two ``create_submission()`` calls (the double-start race) leave exactly
        one in-progress submission; the second call returns the first one."""
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        second = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.assertEqual(self._in_progress_count(), 1)
        self.assertEqual(first.pk, second.pk)

    def test_double_start_cannot_grant_xp_twice(self):
        """The exact reported symptom: a non-repeatable quest cannot be completed
        twice via a double start, so XP is granted only once."""
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        second = QuestSubmission.objects.create_submission(self.student, self.quest)

        # Only one real submission exists; "completing both" is completing the same one.
        first.refresh_from_db()
        first.mark_completed()
        first.mark_approved()
        second.refresh_from_db()
        second.mark_completed()
        second.mark_approved()

        approved = QuestSubmission.objects.filter(
            quest=self.quest, user=self.student, is_completed=True, is_approved=True,
        ).count()
        self.assertEqual(approved, 1)
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), self.quest.xp)


class RepeatableQuestFlowRegressionTest(TenantTestCase):
    """Guard that the constraint is a no-op for legitimate flows: a repeatable
    quest can still accumulate completed submissions, because completing a
    submission moves it out of the constraint's (``is_completed=False``) scope."""

    def setUp(self):
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(
            Quest, name="Repeatable quest", xp=5,
            max_repeats=-1, repeat_per_semester=False,
            published=True, archived=False,
        )

    def test_repeatable_quest_can_start_again_after_completion(self):
        """Completing ordinal 1 then starting ordinal 2 is allowed (the previous
        submission is is_completed=True, so it doesn't collide)."""
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        first.mark_completed()
        first.mark_approved()

        second = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.ordinal, 2)
        self.assertFalse(second.is_completed)
        self.assertEqual(
            QuestSubmission.objects.filter(quest=self.quest, user=self.student).count(), 2,
        )


class MigrationDedupTest(TenantTestCase):
    """Cover migration 0049's ``remove_duplicate_in_progress_submissions``:
    it must delete duplicate in-progress rows (keeping the earliest), skip
    NULL-semester rows, and leave completed submissions untouched."""

    def _constraint(self):
        return next(
            c for c in QuestSubmission._meta.constraints
            if c.name == "unique_inprogress_submission_per_quest_semester"
        )

    def _run_dedup(self):
        with connection.schema_editor() as schema_editor:
            migration_0049.remove_duplicate_in_progress_submissions(
                django_apps, schema_editor,
            )

    def test_migration_dedup_removes_duplicate_in_progress_rows(self):
        """Duplicate in-progress rows (the historical pre-constraint state) are
        deleted keeping the earliest; completed and NULL-semester rows survive."""
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, published=True, archived=False)
        active = SiteConfig.get().active_semester

        # Recreate the historical duplicate state by dropping the constraint first.
        with connection.schema_editor() as schema_editor:
            schema_editor.remove_constraint(QuestSubmission, self._constraint())
        try:
            keeper = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active, is_completed=False,
            )
            duplicate = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active, is_completed=False,
            )
            completed = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active, is_completed=True,
            )
            # NULL-semester rows are skipped by the dedup (NULLs never violate
            # the partial unique index).
            null_sem_1 = baker.make(QuestSubmission, user=student, quest=quest, semester=None, is_completed=False)
            null_sem_2 = baker.make(QuestSubmission, user=student, quest=quest, semester=None, is_completed=False)

            self._run_dedup()

            self.assertTrue(QuestSubmission.objects.filter(pk=keeper.pk).exists())
            self.assertFalse(QuestSubmission.objects.filter(pk=duplicate.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=completed.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=null_sem_1.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=null_sem_2.pk).exists())
        finally:
            # The dedup's deletes leave deferred trigger events pending in the
            # test transaction, and Postgres refuses CREATE INDEX while they
            # exist -- force them to fire before re-adding the constraint.
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            with connection.schema_editor() as schema_editor:
                schema_editor.add_constraint(QuestSubmission, self._constraint())

    def test_migration_dedup_noop_when_no_duplicates(self):
        """With no duplicate rows the dedup deletes nothing (the empty branch)."""
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, published=True, archived=False)
        sub = QuestSubmission.objects.create_submission(student, quest)

        self._run_dedup()

        self.assertTrue(QuestSubmission.objects.filter(pk=sub.pk).exists())
