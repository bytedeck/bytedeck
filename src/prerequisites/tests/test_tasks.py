# When prereq is changed, id is added/removed from cache
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.utils import OperationalError
from django.test import override_settings

from django_tenants.test.client import TenantClient
from model_bakery import baker
from tenant_schemas_celery.task import TenantTask

from badges.models import Badge, BadgeAssertion
from courses.models import CourseStudent
from notifications.models import Notification
from prerequisites.models import Prereq, PrereqAllConditionsMet
from prerequisites.tasks import (
    grant_badge_assertions_for_badge,
    update_conditions_for_quest,
    update_quest_conditions_all_users,
    update_quest_conditions_for_user,
)
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class GrantBadgeAssertionsForBadgeTest(ByteDeckTenantTestCase):
    """Tests for the `grant_badge_assertions_for_badge` task, which grants a badge to
    all current students who meet its (changed) prerequisite conditions. Issue #1157.
    """

    def setUp(self):
        """Set up a teacher, a current-semester student who has completed a quest, and a badge."""
        self.client = TenantClient(self.tenant)
        self.teacher = baker.make(User, is_staff=True)
        self.student = baker.make(User)
        baker.make('courses.CourseStudent', user=self.student,
                   semester=SiteConfig.get().active_semester)

        self.quest = baker.make(Quest)
        self.badge = baker.make(Badge)
        # the student has already completed the quest
        baker.make(QuestSubmission, user=self.student, quest=self.quest,
                   is_completed=True, is_approved=True,
                   semester=SiteConfig.get().active_semester)

    def run_task(self):
        """Run the task synchronously, with the student's teacher patched in."""
        with patch('profile_manager.models.Profile.current_teachers', return_value=[self.teacher]):
            return grant_badge_assertions_for_badge(badge_id=self.badge.id, start_from_user_id=1)

    def test_grant_badge_assertions_for_badge__grants_and_notifies(self):
        """A student who already meets a badge's new prereq conditions is granted the
        badge, and their teacher is notified of the auto-grant.
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        notifications_before = Notification.objects.all_for_user(self.teacher).count()

        self.run_task()

        self.assertTrue(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )
        self.assertEqual(
            Notification.objects.all_for_user(self.teacher).count(), notifications_before + 1
        )

    def test_grant_badge_assertions_for_badge__conditions_not_met(self):
        """A student who doesn't meet the badge's prereq conditions is not granted it."""
        other_quest = baker.make(Quest)  # not completed by the student
        Prereq.add_simple_prereq(self.badge, other_quest)

        self.run_task()

        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__no_prereqs(self):
        """A badge with no prereqs is manually granted only, so the task grants nothing."""
        self.run_task()

        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__already_granted(self):
        """A student who already has the badge is not granted a duplicate."""
        Prereq.add_simple_prereq(self.badge, self.quest)
        BadgeAssertion.objects.create_assertion(self.student, self.badge)

        self.run_task()

        self.assertEqual(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).count(), 1
        )

    def test_grant_badge_assertions_for_badge__unpublished_badge(self):
        """An unpublished badge is never auto-granted."""
        Prereq.add_simple_prereq(self.badge, self.quest)
        self.badge.published = False
        self.badge.full_clean()
        self.badge.save()

        self.run_task()

        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__deleted_badge(self):
        """The task bails out gracefully if the badge was deleted while it was queued."""
        deleted_badge_id = self.badge.id
        self.badge.delete()

        result = grant_badge_assertions_for_badge(badge_id=deleted_badge_id, start_from_user_id=1)

        self.assertIn("no longer exists", result)

    def test_grant_badge_assertions_for_badge__skips_if_already_started(self):
        """The task skips itself when another run for the same badge started recently
        (e.g. a teacher double-clicking the grant button).
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        cache.set(f'grant_badge_assertions_for_badge_{self.badge.id}_wait', True, 1)

        result = self.run_task()

        self.assertIn("already started", result)
        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__no_current_students(self):
        """The task completes without granting anything when there are no students
        registered in a course in the active semester.
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        CourseStudent.objects.all().delete()

        result = self.run_task()

        self.assertEqual(result, self.badge.name)
        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__excludes_students_not_enrolled_this_semester(self):
        """Only students enrolled in a course this semester are granted: a user who meets the
        prereqs but isn't enrolled is skipped, while the enrolled student is granted (issue #2061).
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        # A user who completed the same quest (so meets the prereq) but has no course enrolment.
        unenrolled = baker.make(User)
        baker.make(QuestSubmission, user=unenrolled, quest=self.quest,
                   is_completed=True, is_approved=True, semester=SiteConfig.get().active_semester)

        self.run_task()

        self.assertTrue(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )
        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(unenrolled, self.badge, False).exists()
        )

    def test_grant_badge_assertions_for_badge__excludes_enrolled_staff(self):
        """The grant is for students only: a staff member enrolled as a CourseStudent who meets the
        prereqs is not granted the badge (issue #2061).
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        staff = baker.make(User, is_staff=True)
        baker.make('courses.CourseStudent', user=staff, semester=SiteConfig.get().active_semester)
        baker.make(QuestSubmission, user=staff, quest=self.quest,
                   is_completed=True, is_approved=True, semester=SiteConfig.get().active_semester)

        self.run_task()

        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(staff, self.badge, False).exists()
        )

    @override_settings(CELERY_TASKS_BUNCH_SIZE=1)
    def test_grant_badge_assertions_for_badge__processes_users_in_bunches(self):
        """When there are more users than the bunch size, the task re-queues itself to
        continue with the next bunch of users.
        """
        Prereq.add_simple_prereq(self.badge, self.quest)
        # a second student, so the first bunch (of 1) doesn't cover everyone
        student2 = baker.make(User)
        baker.make('courses.CourseStudent', user=student2,
                   semester=SiteConfig.get().active_semester)

        with patch.object(grant_badge_assertions_for_badge, 'apply_async') as recursive_call:
            self.run_task()

        self.assertEqual(recursive_call.call_count, 1)


class UpdateConditionsForQuestTaskTest(ByteDeckTenantTestCase):
    """Tests for update_conditions_for_quest, which refreshes each relevant user's
    available-quest cache (PrereqAllConditionsMet) for a single quest, in bunches."""

    def setUp(self):
        """A student enrolled in the active semester's course."""
        self.student = baker.make(User)
        baker.make('courses.CourseStudent', user=self.student, semester=SiteConfig.get().active_semester)

    def test_update_conditions_for_quest__missing_quest_returns_message(self):
        """A quest deleted while the task is queued short-circuits with a message."""
        result = update_conditions_for_quest(quest_id=999999, start_from_user_id=1)
        self.assertIn("no longer exists", result)

    def test_update_conditions_for_quest__already_started_is_skipped(self):
        """A fresh run (user 1) is skipped while the short debounce cache key is set."""
        quest = baker.make(Quest)
        cache_key = f'update_conditions_for_quest_{quest.id}_wait'
        cache.set(cache_key, True, 10)
        try:
            result = update_conditions_for_quest(quest_id=quest.id, start_from_user_id=1)
        finally:
            cache.delete(cache_key)
        self.assertIn("already started", result)

    def test_update_conditions_for_quest__course_scoped_quest_removes_unmet_from_cache(self):
        """For a course-scoped quest whose prereq the student hasn't met, the quest is
        left out of the student's available-quest cache (the not-available branch)."""
        quest = baker.make(Quest, available_outside_course=False)
        unmet_prereq = baker.make(Quest)
        Prereq.add_simple_prereq(quest, unmet_prereq)  # student has not completed unmet_prereq

        with patch.object(update_conditions_for_quest, 'apply_async'):  # don't recurse for real
            result = update_conditions_for_quest(quest_id=quest.id, start_from_user_id=1)

        self.assertEqual(result, quest.name)
        cache_obj = PrereqAllConditionsMet.objects.get(user=self.student, model_name=Quest.get_model_name())
        self.assertNotIn(quest.id, cache_obj.get_ids())

    @override_settings(CELERY_TASKS_BUNCH_SIZE=1)
    def test_update_conditions_for_quest__requeues_for_the_next_bunch(self):
        """With more users than the bunch size, the task re-queues itself for the next user."""
        baker.make(User)  # ensure a second user exists beyond the first bunch of 1
        quest = baker.make(Quest, available_outside_course=True)  # -> every user
        with patch.object(update_conditions_for_quest, 'apply_async') as recursive_call:
            update_conditions_for_quest(quest_id=quest.id, start_from_user_id=1)
        self.assertEqual(recursive_call.call_count, 1)
        self.assertEqual(recursive_call.call_args.kwargs['kwargs']['quest_id'], quest.id)


class UpdateQuestConditionsForUserTaskTest(ByteDeckTenantTestCase):
    """Tests for update_quest_conditions_for_user, which recomputes one user's whole
    available-quest cache."""

    def test_update_quest_conditions_for_user__missing_user_returns_none(self):
        """A user deleted while the task is queued short-circuits and returns None."""
        self.assertIsNone(update_quest_conditions_for_user(user_id=999999))


class UpdateQuestConditionsAllUsersTaskTest(ByteDeckTenantTestCase):
    """Tests for update_quest_conditions_all_users, which fans out per-user cache
    recomputation across the active semester's students, in bunches."""

    def setUp(self):
        """Two students enrolled in the active semester's course."""
        sem = SiteConfig.get().active_semester
        self.student_a = baker.make(User)
        self.student_b = baker.make(User)
        baker.make('courses.CourseStudent', user=self.student_a, semester=sem)
        baker.make('courses.CourseStudent', user=self.student_b, semester=sem)
        cache.delete('update_conditions_all_task_waiting')

    def test_update_quest_conditions_all_users__already_running_is_skipped(self):
        """A fresh run (user 1) is skipped while the debounce cache key is set."""
        cache.set('update_conditions_all_task_waiting', True, 60)
        try:
            result = update_quest_conditions_all_users(start_from_user_id=1)
        finally:
            cache.delete('update_conditions_all_task_waiting')
        self.assertEqual(result, "Skipping task, already running.")

    @override_settings(CELERY_TASKS_BUNCH_SIZE=1)
    def test_update_quest_conditions_all_users__dispatches_per_user_and_requeues(self):
        """Each user in the bunch gets a per-user recompute dispatched, and the task
        re-queues itself for the next bunch when more users remain."""
        with patch.object(update_quest_conditions_for_user, 'apply_async') as per_user_call, \
             patch.object(update_quest_conditions_all_users, 'apply_async') as recursive_call:
            update_quest_conditions_all_users(start_from_user_id=1)
        self.assertEqual(per_user_call.call_count, 1)   # one user in the bunch of 1
        self.assertEqual(recursive_call.call_count, 1)  # more users remain -> recurse


class TransactionAwareTaskTest(ByteDeckTenantTestCase):
    """Tests for TransactionAwareTask.apply_async, which defers queuing until the
    surrounding DB transaction commits and handles connection errors."""

    def test_apply_async__operational_error_retries_with_doubled_countdown(self):
        """An OperationalError while scheduling the on-commit hook retries immediately
        with the countdown doubled."""
        with patch('prerequisites.tasks.transaction.on_commit', side_effect=OperationalError), \
             patch.object(TenantTask, 'apply_async', return_value='queued') as super_call:
            result = update_quest_conditions_for_user.apply_async(kwargs={'user_id': 1}, countdown=60)
        super_call.assert_called_once()
        self.assertEqual(super_call.call_args.kwargs['countdown'], 120)
        self.assertEqual(result, 'queued')

    def test_apply_async__unexpected_error_is_logged_and_swallowed(self):
        """Any other error scheduling the on-commit hook is logged and swallowed (returns None)."""
        with patch('prerequisites.tasks.transaction.on_commit', side_effect=ValueError), \
             patch.object(TenantTask, 'apply_async') as super_call:
            result = update_quest_conditions_for_user.apply_async(kwargs={'user_id': 1})
        super_call.assert_not_called()
        self.assertIsNone(result)
