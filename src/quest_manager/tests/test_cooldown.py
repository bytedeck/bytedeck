"""Tests for the repeatable-quest cooldown "available again soon" surface (issue #57)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from django_tenants.test.client import TenantClient
from freezegun import freeze_time
from model_bakery import baker

from courses.models import CourseStudent
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class CooldownTestMixin:
    """Shared setup: a student enrolled this semester with a completed repeatable (24h cooldown) quest."""

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, an enrolled student, and a repeatable quest the student just completed."""
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student')
        cls.semester = SiteConfig.get().active_semester
        baker.make(CourseStudent, user=cls.test_student, semester=cls.semester)

        # unlimited repeats, 24h cooldown between them
        cls.quest = baker.make(Quest, name="Daily Quest", max_repeats=-1, hours_between_repeats=24)

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def _complete(self, quest=None):
        """Create and complete a submission of `quest` (defaults to self.quest) for the student."""
        quest = quest or self.quest
        sub = QuestSubmission.objects.create_submission(self.test_student, quest)
        sub.mark_completed()
        return sub


class NextRepeatAvailableModelTests(CooldownTestMixin, ByteDeckTenantTestCase):

    def test_next_repeat_available__none_when_not_repeatable(self):
        """A non-repeatable quest never has a next-repeat time."""
        one_off = baker.make(Quest, max_repeats=0, repeat_per_semester=False)
        QuestSubmission.objects.create_submission(self.test_student, one_off).mark_completed()
        self.assertIsNone(one_off.next_repeat_available(self.test_student))

    def test_next_repeat_available__none_when_never_completed(self):
        """A repeatable quest the student hasn't completed has no next-repeat time."""
        self.assertIsNone(self.quest.next_repeat_available(self.test_student))

    def test_next_repeat_available__future_while_in_cooldown(self):
        """Right after completion, the next-repeat time is the cooldown window into the future."""
        self._complete()
        next_at = self.quest.next_repeat_available(self.test_student)
        self.assertIsNotNone(next_at)
        # ~24h from now (allow a little slack for execution time)
        self.assertGreater(next_at, timezone.now() + timedelta(hours=23))
        self.assertLess(next_at, timezone.now() + timedelta(hours=25))

    def test_next_repeat_available__in_past_once_cooldown_elapsed(self):
        """Once the cooldown has elapsed, the next-repeat time is in the past (available now)."""
        with freeze_time(timezone.now() - timedelta(hours=25)):
            self._complete()
        next_at = self.quest.next_repeat_available(self.test_student)
        self.assertIsNotNone(next_at)
        self.assertLess(next_at, timezone.now())

    def test_next_repeat_available__none_when_repeat_cap_reached(self):
        """A quest at its repeat cap won't come back, so it has no next-repeat time."""
        capped = baker.make(Quest, max_repeats=1, hours_between_repeats=24)
        self._complete(capped)  # ordinal 1
        self._complete(capped)  # ordinal 2 > max_repeats=1 → capped out
        self.assertIsNone(capped.next_repeat_available(self.test_student))

    def test_next_repeat_available__none_when_per_semester_cap_reached(self):
        """A once-per-semester quest already done this semester won't come back until next semester."""
        per_sem = baker.make(Quest, max_repeats=0, repeat_per_semester=True, hours_between_repeats=24)
        self._complete(per_sem)  # one completion this semester == the per-semester cap
        self.assertIsNone(per_sem.next_repeat_available(self.test_student))

    def test_next_repeat_available__none_when_latest_attempt_in_progress(self):
        """With only an in-progress (never-completed) attempt, there's no next-repeat time."""
        QuestSubmission.objects.create_submission(self.test_student, self.quest)  # started, not completed
        self.assertIsNone(self.quest.next_repeat_available(self.test_student))


class GetInCooldownManagerTests(CooldownTestMixin, ByteDeckTenantTestCase):

    def test_get_in_cooldown__includes_quest_while_in_cooldown(self):
        """A just-completed repeatable quest appears in the cooldown list (and not in available)."""
        self._complete()
        self.assertIn(self.quest, Quest.objects.get_in_cooldown(self.test_student))
        self.assertNotIn(self.quest, Quest.objects.get_available(self.test_student))

    def test_get_in_cooldown__empty_once_cooldown_elapsed(self):
        """After the cooldown passes the quest leaves the cooldown list (it's available again)."""
        with freeze_time(timezone.now() - timedelta(hours=25)):
            self._complete()
        self.assertNotIn(self.quest, Quest.objects.get_in_cooldown(self.test_student))
        self.assertIn(self.quest, Quest.objects.get_available(self.test_student))

    def test_get_in_cooldown__excludes_in_progress_quest(self):
        """A quest with an in-progress (uncompleted / just-started) attempt is not shown as in cooldown."""
        QuestSubmission.objects.create_submission(self.test_student, self.quest)  # started, not completed
        self.assertNotIn(self.quest, Quest.objects.get_in_cooldown(self.test_student))

    def test_get_in_cooldown__excludes_quest_with_returned_attempt(self):
        """A quest whose latest attempt was returned (still in progress) is not shown as in cooldown."""
        self._complete()  # attempt 1 completed → would otherwise be in cooldown
        returned = QuestSubmission.objects.create_submission(self.test_student, self.quest)  # attempt 2
        returned.mark_completed()
        returned.mark_returned()  # teacher returns it → is_completed=False (an active, in-progress submission)
        self.assertNotIn(self.quest, Quest.objects.get_in_cooldown(self.test_student))

    def test_get_in_cooldown__excludes_non_repeatable_quest(self):
        """A completed non-repeatable quest is never in the cooldown list."""
        one_off = baker.make(Quest, name="One Off", max_repeats=0, repeat_per_semester=False)
        self._complete(one_off)
        self.assertNotIn(one_off, Quest.objects.get_in_cooldown(self.test_student))


class CooldownViewTests(CooldownTestMixin, ViewTestUtilsMixin, ByteDeckTenantTestCase):

    def test_quest_list__available_tab_lists_cooldown_quest(self):
        """The Available tab shows a completed-in-cooldown quest with its countdown."""
        self._complete()
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('quests:available'))
        self.assertIn(self.quest, response.context['cooldown_quests'])
        self.assertContains(response, "Available again soon")

    def test_quest_list__no_cooldown_section_without_cooldown_quests(self):
        """With nothing in cooldown, the Available tab omits the cooldown section."""
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('quests:available'))
        self.assertEqual(list(response.context['cooldown_quests']), [])
        self.assertNotContains(response, "Available again soon")

    def test_start__already_in_progress_shows_message(self):
        """Starting a quest that's already in progress redirects to it with an explanatory message."""
        sub = QuestSubmission.objects.create_submission(self.test_student, self.quest)
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('quests:start', args=[self.quest.id]), follow=True)
        self.assertRedirects(response, sub.get_absolute_url())
        self.assertContains(response, "already have")
