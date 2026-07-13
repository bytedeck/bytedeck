# When prereq is changed, id is added/removed from cache
from unittest.mock import patch

from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from badges.models import Badge, BadgeAssertion
from notifications.models import Notification
from prerequisites.models import Prereq
from prerequisites.tasks import grant_badge_assertions_for_badge
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class GrantBadgeAssertionsForBadgeTest(TenantTestCase):
    """Tests for the `grant_badge_assertions_for_badge` task, which grants a badge to
    all current students who meet its (changed) prerequisite conditions. Issue #1157.
    """

    def setUp(self):
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
        self.badge.save()

        self.run_task()

        self.assertFalse(
            BadgeAssertion.objects.all_for_user_badge(self.student, self.badge, False).exists()
        )
