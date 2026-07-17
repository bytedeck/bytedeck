"""Regression tests for issue #1345 -- "Quests are at times repeatable when
they shouldn't be".

A concurrent "double start" (a student opening two browser tabs and starting the
same non-repeatable quest before either submission is committed) could create two
in-progress submissions of the same quest. Both could then be completed and
approved, granting XP twice.

The fix is a partial unique constraint forbidding more than one
*never-yet-completed* in-progress (``is_completed=False`` and
``first_time_completed IS NULL``) submission per ``(user, quest, semester)``,
plus ``create_submission()`` catching the resulting ``IntegrityError`` and
returning the submission that won the race instead of a duplicate. Returned
submissions (``first_time_completed`` set) are exempt, so a teacher returning an
old submission of a repeatable quest while a new one is in progress stays legal.
"""
import importlib
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()

# The migration module starts with a digit, so it can't be imported with a
# plain ``import`` statement.
migration_0049 = importlib.import_module(
    "quest_manager.migrations.0049_inprogress_submission_unique_constraint"
)


class DoubleStartRaceTest(ByteDeckTenantTestCase):
    """The concurrent-double-start vector from issue #1345."""

    def setUp(self):
        """Create a student and a non-repeatable published quest, and grab the
        active semester the submissions will land in."""
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(
            Quest, name="One-time quest", xp=10,
            max_repeats=0, repeat_per_semester=False,
            published=True, archived=False,
        )
        self.active_semester = SiteConfig.get().active_semester

    def _in_progress_count(self):
        """Return how many in-progress (not completed) submissions of the test
        quest the test student currently has."""
        return QuestSubmission.objects.filter(
            quest=self.quest, user=self.student, is_completed=False,
        ).count()

    def test_save__second_fresh_in_progress_submission_raises_integrity_error(self):
        """Saving a second never-completed in-progress submission of the same
        quest/semester raises IntegrityError (the DB-level guard)."""
        QuestSubmission.objects.create_submission(self.student, self.quest)

        duplicate = QuestSubmission(
            quest=self.quest, user=self.student, ordinal=2,
            semester_id=self.active_semester.pk,
        )
        with self.assertRaises(IntegrityError):
            # Wrapped so the failed statement doesn't poison the test transaction.
            with transaction.atomic():
                # Constraint validation skipped so the DB constraint itself
                # (the behaviour under test) raises, not full_clean.
                duplicate.full_clean(validate_constraints=False)
                duplicate.save()

    def test_create_submission__reraises_integrity_error_when_not_the_race(self):
        """An IntegrityError that is NOT the double-start race (no matching
        in-progress submission exists to recover) is re-raised, not swallowed."""
        with mock.patch.object(
            QuestSubmission, "save", side_effect=IntegrityError("not the double-start race"),
        ):
            with self.assertRaises(IntegrityError):
                QuestSubmission.objects.create_submission(self.student, self.quest)

        # Nothing was created and nothing was silently returned.
        self.assertEqual(self._in_progress_count(), 0)

    def test_create_submission__twice_returns_existing_and_makes_no_duplicate(self):
        """Two ``create_submission()`` calls (the double-start race) leave exactly
        one in-progress submission; the second call returns the first one."""
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        second = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.assertEqual(self._in_progress_count(), 1)
        self.assertEqual(first.pk, second.pk)

    def test_create_submission__double_start_cannot_grant_xp_twice(self):
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


class RepeatableQuestFlowRegressionTest(ByteDeckTenantTestCase):
    """Guard that the constraint is a no-op for legitimate flows: a repeatable
    quest can still accumulate completed submissions (completing a submission
    moves it out of the constraint's scope), and a teacher can still *return* an
    old submission while a new one is in progress."""

    def setUp(self):
        """Create a student and an infinitely repeatable published quest."""
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(
            Quest, name="Repeatable quest", xp=5,
            max_repeats=-1, repeat_per_semester=False,
            published=True, archived=False,
        )

    def test_create_submission__repeatable_quest_can_start_again_after_completion(self):
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

    def test_mark_returned__allowed_while_new_submission_in_progress(self):
        """A teacher can return an old submission of a repeatable quest while the
        student already has a new one in progress (two "in progress" rows, only
        one never-completed) -- the constraint must not break this workflow.

        ``mark_returned()`` flips ``is_completed`` back to False, but the
        returned row keeps its ``first_time_completed``, which exempts it from
        the partial unique constraint.
        """
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        first.mark_completed()
        first.mark_approved()

        second = QuestSubmission.objects.create_submission(self.student, self.quest)
        self.assertFalse(second.is_completed)

        # The reviewer-raised scenario: returning the old submission while the
        # new one is in progress must not raise IntegrityError.
        first.mark_returned()

        first.refresh_from_db()
        self.assertFalse(first.is_completed)
        self.assertIsNotNone(first.first_time_completed)  # what exempts it
        self.assertEqual(
            QuestSubmission.objects.filter(
                quest=self.quest, user=self.student, is_completed=False,
            ).count(),
            2,
        )


class MigrationDedupTest(ByteDeckTenantTestCase):
    # Drops and re-adds the QuestSubmission unique constraint via the schema
    # editor, so give it a private fresh schema rather than mutating the shared
    # reused one (and to avoid colliding with the persistent test tenant).
    reuse_schema = False

    """Cover migration 0049's ``remove_duplicate_in_progress_submissions``:
    it must delete duplicate never-completed in-progress rows (keeping the
    earliest, flushing deletes in bounded batches) and spare completed,
    returned, and NULL-semester rows."""

    def _constraint(self):
        """Return the partial unique constraint object from QuestSubmission's
        Meta, so tests can drop and re-add it via the schema editor."""
        return next(
            c for c in QuestSubmission._meta.constraints
            if c.name == "unique_inprogress_submission_per_quest_semester"
        )

    def _run_dedup(self):
        """Invoke the migration's dedup function against the current (test)
        schema, exactly as RunPython would."""
        with connection.schema_editor() as schema_editor:
            migration_0049.remove_duplicate_in_progress_submissions(
                django_apps, schema_editor,
            )

    def test_remove_duplicate_in_progress_submissions__removes_duplicates_spares_rest(self):
        """Duplicate fresh in-progress rows (the historical pre-constraint state)
        are deleted keeping the earliest -- in bounded batches -- while completed,
        returned, and NULL-semester rows survive."""
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
            # Three duplicates + a batch size of 2 (patched below) exercises both
            # the mid-loop batch flush and the final leftover flush.
            duplicates = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active,
                is_completed=False, _quantity=3,
            )
            completed = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active, is_completed=True,
            )
            # A *returned* submission (in progress again, but first_time_completed
            # set) must be skipped by the dedup even alongside a fresh in-progress
            # row -- it's exempt from the constraint.
            returned = baker.make(
                QuestSubmission, user=student, quest=quest, semester=active,
                is_completed=False, first_time_completed=timezone.now(),
            )
            # NULL-semester rows are skipped by the dedup (NULLs never violate
            # the partial unique index).
            null_sem_1 = baker.make(QuestSubmission, user=student, quest=quest, semester=None, is_completed=False)
            null_sem_2 = baker.make(QuestSubmission, user=student, quest=quest, semester=None, is_completed=False)

            with mock.patch.object(migration_0049, "DEDUP_BATCH_SIZE", 2):
                self._run_dedup()

            self.assertTrue(QuestSubmission.objects.filter(pk=keeper.pk).exists())
            for duplicate in duplicates:
                self.assertFalse(QuestSubmission.objects.filter(pk=duplicate.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=completed.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=returned.pk).exists())
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

    def test_remove_duplicate_in_progress_submissions__noop_when_no_duplicates(self):
        """With no duplicate rows the dedup deletes nothing (the empty branch)."""
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, published=True, archived=False)
        sub = QuestSubmission.objects.create_submission(student, quest)

        self._run_dedup()

        self.assertTrue(QuestSubmission.objects.filter(pk=sub.pk).exists())
