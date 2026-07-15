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
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


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
