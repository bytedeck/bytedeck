import datetime
import re
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.utils import timezone

from django_tenants.test.client import TenantClient
from freezegun import freeze_time
from model_bakery import baker
from model_bakery.recipe import Recipe
from comments.models import Comment

from courses.models import Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Category, CommonData, Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class CategoryTestModel(ByteDeckTenantTestCase):  # aka Campaigns
    @classmethod
    def setUpTestData(cls):
        """Create a test campaign (Category) shared across the tests."""
        cls.category = baker.make(Category, title="Test Campaign")

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_category__creation_and_str(self):
        """Creating a Category yields a Category instance whose str is its title."""
        self.assertIsInstance(self.category, Category)
        self.assertEqual(str(self.category), self.category.title)

    def test_condition_met_as_prerequisite__all_unique_quests_completed(self):
        """ Test that all unique quests in a campaign are completed before the campaign is considered completed
        for prerequisite purposes. Make sure multiple completions of repeatable quests don't count. """

        user = baker.make('user')
        user2 = baker.make('user')

        # create some quests as part of the test campaign
        quest1_repeatable = baker.make(Quest, campaign=self.category, max_repeats=-1)  # repeatable
        quest2 = baker.make(Quest, campaign=self.category)

        # user should not meet the prerequisite at this point (no quests completed)
        self.assertFalse(self.category.condition_met_as_prerequisite(user))

        # create and complete a quest submission for the first quest, still doesn't meet prereq
        baker.make(QuestSubmission, quest=quest1_repeatable, user=user, is_completed=True, is_approved=True)
        self.assertFalse(self.category.condition_met_as_prerequisite(user))

        # complete the repeatable quest a second time, category prereq should still not be met
        baker.make(QuestSubmission, quest=quest1_repeatable, user=user, is_completed=True, is_approved=True)
        self.assertFalse(self.category.condition_met_as_prerequisite(user))

        # create a quest submission for the second quest, now they should meet the prereq
        baker.make(QuestSubmission, quest=quest2, user=user, is_completed=True, is_approved=True)
        self.assertTrue(self.category.condition_met_as_prerequisite(user))

        # But other random user still doesn't meet prereq
        self.assertFalse(self.category.condition_met_as_prerequisite(user2))

    def test_condition_met_as_prerequisite__draft_and_archived_quests(self):
        """ Test that published=False (draft) and archived quests
        are not needed when checking if campaign is met as a prerequisite.
        """
        user = baker.make('user')

        quest1 = baker.make(Quest, campaign=self.category)
        # draft quest shouldn't be required to fulfill campaign
        baker.make(Quest, campaign=self.category, published=False)
        # archived quest shouldn't be required
        baker.make(Quest, campaign=self.category, archived=True)

        # user should not meet the prerequisite at this point (no quests completed)
        self.assertFalse(self.category.condition_met_as_prerequisite(user))

        # create and complete a quest submission for the first quest,
        # should now meet Campaign prereq because
        # - quest2 is a draft,
        # - quest3 is archived
        baker.make(QuestSubmission, quest=quest1, user=user, is_completed=True, is_approved=True)
        self.assertTrue(self.category.condition_met_as_prerequisite(user))

    def test_get_absolute_url__category_page_loads(self):
        """The campaign's absolute URL is reachable and returns 200."""
        self.assertEqual(self.client.get(self.category.get_absolute_url(), follow=True).status_code, 200)

    def test_current_quests__returns_published_unarchived_quests(self):
        """ Test that the queryset of all quests in a campaign is returned correctly """

        # assert that the current campaign has no quests
        self.assertEqual(self.category.current_quests().count(), 0)

        # create some quests as part of the test campaign, some are invalid and won't be included
        baker.make(Quest, campaign=self.category)  # included in queryset
        baker.make(Quest, campaign=self.category)  # included in queryset
        baker.make(Quest, campaign=self.category, published=False)  # NOT included in queryset because not published
        baker.make(Quest, campaign=self.category, archived=True)  # NOT included in queryset because archived
        baker.make(Quest)  # NOT included in queryset because in a different campaign

        # assert that the current campaign has 2 valid quests after additions
        self.assertEqual(self.category.current_quests().count(), 2)

    def test_xp_sum__sums_quest_xp(self):
        """ Test that the XP sum of all quests in a campaign is returned correctly """

        # create some quests as part of the test campaign
        baker.make(Quest, campaign=self.category, xp=1)
        baker.make(Quest, campaign=self.category, xp=2)

        # check that the XP sum is correct
        self.assertEqual(self.category.xp_sum(), 3)

    def test_quest_count__counts_quests(self):
        """ Test that the number of all quests in a campaign is returned correctly """

        # assert that the current campaign has no quests
        self.assertEqual(self.category.quest_count(), 0)

        # create some quests as a part of the test campaign
        baker.make(Quest, campaign=self.category)
        baker.make(Quest, campaign=self.category)

        # check that the quest count is correct after additions
        self.assertEqual(self.category.quest_count(), 2)


class CommonDataTestModel(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Create a CommonData instance shared across the tests."""
        cls.common_data = baker.make(CommonData)

    def test_common_data__creation_and_str(self):
        """Creating CommonData yields a CommonData instance whose str is its title."""
        self.assertIsInstance(self.common_data, CommonData)
        self.assertEqual(str(self.common_data), self.common_data.title)


class QuestTestModel(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a Quest shared across the tests."""
        cls.quest = baker.make(Quest)

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_quest__creation_and_str(self):
        """Creating a Quest yields a Quest instance whose str is its name."""
        self.assertIsInstance(self.quest, Quest)
        self.assertEqual(str(self.quest), self.quest.name)

    def test_get_absolute_url__quest_page_loads(self):
        """The quest's absolute URL is reachable and returns 200."""
        self.assertEqual(self.client.get(self.quest.get_absolute_url(), follow=True).status_code, 200)

    def test_active__false_for_unavailable_expired_or_hidden_quests(self):
        """
        The active method of the Quest model's parent "XPItem" should return the correct values based on a quest object's settings.

        Quest.active should return False if:
        1. The quest has an availability date/time that hasn't yet been reached (date_available, time_available are in the future)
        2. The quest is expired (Quest.expired == False; date_expired, time_expired are in the past)
        3. The quest is a part of an inactive campaign (Quest.campaign == True and Quest.campaign.active == False)
        4. The quest is manually set to be not published (Quest.published == False)
        5. The quest is archived
        """

        # create and test a control quest that will return active by default
        q = baker.make(Quest)
        self.assertTrue(q.active)

        # create and test a quest that won't be available until one day later
        q = baker.make(Quest, date_available=(timezone.localtime() + timezone.timedelta(days=1)).date())
        self.assertFalse(q.active)

        # create and test a quest that won't be available until one hour later in the same day
        # using freeze_time to prevent time_available from looping from 23:00 to 0:00 when adding 1 hour
        dt = datetime.datetime(2024, 1, 1, 6, tzinfo=timezone.get_current_timezone())
        with freeze_time(dt):
            q = baker.make(
                Quest,
                date_available=timezone.localdate(),
                time_available=(timezone.localtime() + timezone.timedelta(hours=1)).time()
            )
            self.assertFalse(q.active)

        dt = timezone.datetime(2023, 6, 13, 12, 0, 0).replace(tzinfo=timezone.get_current_timezone())
        with freeze_time(dt):
            # Quest that expires an hour ago
            dt_expired = timezone.localtime() - timezone.timedelta(hours=1)
            q = baker.make(Quest, time_expired=dt_expired.time())
            self.assertFalse(q.active)

            # create and test a quest that's expired one day ago
            dt_expired = timezone.localtime() - timezone.timedelta(days=1)
            q = baker.make(Quest, date_expired=dt_expired.date())
            self.assertFalse(q.active)

        # create and test a quest that's a part of an inactive campaign
        inactive_campaign = baker.make(Category, title="inactive-campaign", published=False)
        q = baker.make(Quest, campaign=inactive_campaign)
        self.assertFalse(q.active)

        # create and test a quest that's not published
        q = baker.make(Quest, published=False)
        self.assertFalse(q.active)

        # create and test a quest that's archived
        q = baker.make(Quest, archived=True)
        self.assertFalse(q.active)

    def test_expired__date_blank(self):
        """If `date_expired` is blank, expire at `time_expired` every day

        Test that a quest with time_expired set to noon, is available before local noon
        and not available after local noon
        """

        # Get the current local time zone
        local_tz = timezone.get_current_timezone()
        # Create a datetime object for noon on June 13th (arbitrary date)
        dt = timezone.datetime(2023, 6, 13, 12, 0, 0).replace(tzinfo=local_tz)

        # Quest that expires at noon, date_expired=None by default
        quest = baker.make(Quest, time_expired=dt.time())

        # Test a minute before noon
        with freeze_time(dt - timezone.timedelta(minutes=1)):
            self.assertFalse(quest.expired())

        # Test a minute after noon
        with freeze_time(dt + timezone.timedelta(minutes=1)):
            self.assertTrue(quest.expired())

    def test_expired__time_blank(self):
        """If `time_expired` is blank, then assume expiry at midnight on `date_expired`
        """

        # Get the current local time zone
        local_tz = timezone.get_current_timezone()
        # Create a datetime object for noon on June 13th (arbitrary date)
        dt = timezone.datetime(2023, 6, 13, 12, 0, 0).replace(tzinfo=local_tz)

        # Quest that expires on June 13th, time_expired=None by default
        quest = baker.make(Quest, date_expired=dt.date())

        # Test June 13th, should be available because doesn't expire until midnight
        with freeze_time(dt):
            self.assertFalse(quest.expired())

        # Test in 11 hours (11pm), should still be available
        with freeze_time(dt + timezone.timedelta(hours=11)):
            self.assertFalse(quest.expired())

        # Test in 12 hours (aka midnight the next day), should be expired now
        with freeze_time(dt + timezone.timedelta(hours=12)):
            self.assertTrue(quest.expired())

    def test_quest_html_formatting__no_linebreaks_around_span(self):
        """Saving a quest reformats instructions without adding line breaks around span tags."""
        test_markup = "<p>this <span>span</span> tag should not break</p>"
        self.quest.instructions = test_markup
        # Auto formatting on save
        self.quest.save()
        formatted_markup = self.quest.instructions

        # search for line breaks before or after span tags
        matches_found = re.search('(([ ]+)?\n([ ]+)?</?span>)|(</?span>([ ]+)?\n([ ]+)?)', formatted_markup)
        self.assertIsNone(matches_found)

    @freeze_time('2018-10-12 00:54:00', tz_offset=0)
    def test_is_repeat_available__various_repeat_settings(self):
        """
        QuestManager.is_repeat_available should return True if:
            1. it is repeatable (is_repeatable != 0)
            2. the cooldown time has passed for the quest since the last completion
            3. the max repeats have not been completed already (by semester or overall)

        Assumes there has already been at least one submission (change that?)

        def test_is_repeat_available(self, user):"""

        baker.make(User, is_staff=True)  # need a teacher or student creation will fail.
        student = baker.make(User)
        quest_not_repeatable = baker.make(Quest, name="quest-not-repeatable")
        quest_infinite_repeat = baker.make(Quest, name="quest-infinite-repeatable", max_repeats=-1)
        quest_repeat_1hr = baker.make(Quest, name="quest-repeatable-1hr", max_repeats=1, hours_between_repeats=1)
        quest_semester_repeat = baker.make(Quest, name="quest-semester-repeatable", max_repeats=1,
                                           repeat_per_semester=True)
        quest_semester = baker.make(Quest, name="quest-semester", max_repeats=0, repeat_per_semester=True)

        # TESTS WITH NOT REPEATABLE QUEST
        sub_not_repeatable = QuestSubmission.objects.create_submission(student, quest_not_repeatable)
        # non-repeatable quest is not available again.
        self.assertFalse(quest_not_repeatable.is_repeat_available(student))
        # even when completed
        sub_not_repeatable.mark_completed()
        self.assertFalse(quest_not_repeatable.is_repeat_available(student))
        # and when approved
        sub_not_repeatable.mark_approved()
        self.assertFalse(quest_not_repeatable.is_repeat_available(student))

        # TESTS WITH INFINITE REPEATABLE QUEST, 0HRS COOLDOWN
        # in progress, shouldn't be available.
        sub_infinite_repeatable = QuestSubmission.objects.create_submission(student, quest_infinite_repeat)
        self.assertFalse(quest_infinite_repeat.is_repeat_available(student))
        # available after completion
        sub_infinite_repeatable.mark_completed()
        self.assertTrue(quest_infinite_repeat.is_repeat_available(student))
        # and when approved
        sub_infinite_repeatable.mark_approved()
        self.assertTrue(quest_infinite_repeat.is_repeat_available(student))

        # TESTS WITH REPEATABLE QUEST, 1HRS COOLDOWN
        # started
        sub_repeat_1hr = QuestSubmission.objects.create_submission(student, quest_repeat_1hr)
        self.assertFalse(quest_repeat_1hr.is_repeat_available(student))
        sub_repeat_1hr.mark_completed()

        # jump ahead an hour so repeat cooldown is over
        with freeze_time(timezone.localtime() + timezone.timedelta(hours=1, minutes=1)):
            self.assertTrue(quest_repeat_1hr.is_repeat_available(student))
            # start another one
            QuestSubmission.objects.create_submission(student, quest_repeat_1hr)
            self.assertFalse(quest_repeat_1hr.is_repeat_available(student))

        # TESTS WITH REPEATABLE QUEST, BY SEMESTER
        # started
        sub_repeat_semester = QuestSubmission.objects.create_submission(student, quest_semester_repeat)
        self.assertFalse(quest_semester_repeat.is_repeat_available(student))
        sub_repeat_semester.mark_completed()
        # one repeat avail per semester
        self.assertTrue(quest_semester_repeat.is_repeat_available(student))

        sub_repeat_semester2 = QuestSubmission.objects.create_submission(student, quest_semester_repeat)
        sub_repeat_semester2.mark_completed()
        # Ran out this semester
        self.assertFalse(quest_semester_repeat.is_repeat_available(student))

        # TEST NO REPEAT, BUT YES SEMESTER
        # started
        sub_semester = QuestSubmission.objects.create_submission(student, quest_semester)
        self.assertFalse(quest_semester.is_repeat_available(student))
        sub_semester.mark_completed()
        # No repeat left this semester
        self.assertFalse(quest_semester.is_repeat_available(student))

        # change semesters and the quest should appear
        new_active_sem = baker.make(Semester)
        SiteConfig.get().set_active_semester(new_active_sem.id)
        self.assertTrue(quest_semester_repeat.is_repeat_available(student))

        # Repeat this semester, another two should be available

        sub_repeat_semester = QuestSubmission.objects.create_submission(student, quest_semester_repeat)
        self.assertFalse(quest_semester_repeat.is_repeat_available(student))
        sub_repeat_semester.mark_completed()

        # one repeat avail per semester
        self.assertTrue(quest_semester_repeat.is_repeat_available(student))

        sub_repeat_semester2 = QuestSubmission.objects.create_submission(student, quest_semester_repeat)
        sub_repeat_semester2.mark_completed()

        # Ran out this semester
        self.assertFalse(quest_semester_repeat.is_repeat_available(student))

        # TEST NO REPEAT, BUT YES SEMESTER, in this new semester
        self.assertTrue(quest_semester.is_repeat_available(student))
        # started
        sub_semester = QuestSubmission.objects.create_submission(student, quest_semester)
        self.assertFalse(quest_semester.is_repeat_available(student))
        sub_semester.mark_completed()
        # No repeat left this semester
        self.assertFalse(quest_semester.is_repeat_available(student))

    def test_ordinal__increments_and_continues_after_delete(self):
        """Submission ordinals increment and keep counting up even after an earlier submission is deleted."""
        student = baker.make('user')
        quest = baker.make(Quest, max_repeats=-1)

        # ordinal should be 1
        submission1 = QuestSubmission.objects.create_submission(student, quest)
        submission1.mark_completed()
        self.assertEqual(submission1.ordinal, 1)

        # ordinal should be 2
        submission2 = QuestSubmission.objects.create_submission(student, quest)
        submission2.mark_completed()
        self.assertEqual(submission2.ordinal, 2)

        # Delete the first submission
        submission1.delete()

        # ordinal should be 3 since the last ordinal is 2 even though submission1 has been deleted
        submission3 = QuestSubmission.objects.create_submission(student, quest)
        self.assertEqual(submission3.ordinal, 3)


class SubmissionManagerTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Capture the active semester shared across the tests."""
        cls.active_semester = SiteConfig.get().active_semester

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_all_approved__filters_by_semester_quest_and_user(self):
        """ Tests of QuestSubmissionManager.all_approved()
        def all_approved(self, user=None, quest=None, up_to_date=None, active_semester_only=True):
        """

        quest = baker.make(Quest, name="test quest")
        user = baker.make(User, username="test_user")

        # various submissions
        baker.make(QuestSubmission, semester=self.active_semester)  # in progress shoulnd't appear
        baker.make(QuestSubmission, is_completed=True, semester=self.active_semester)  # completed/submitted shouldn't appear
        sub_approved = baker.make(QuestSubmission, quest=quest, is_completed=True, is_approved=True, semester=self.active_semester)
        sub_approved_different_quest = baker.make(QuestSubmission, is_completed=True, is_approved=True, semester=self.active_semester)
        sub_approved_other_semester = baker.make(QuestSubmission, quest=quest, is_completed=True, is_approved=True)
        sub_approved_no_xp = baker.make(QuestSubmission, quest=quest, is_completed=True, is_approved=True,
                                        do_not_grant_xp=True, semester=self.active_semester)
        sub_approved_user = baker.make(QuestSubmission, user=user, quest=quest, is_completed=True, is_approved=True,
                                       semester=self.active_semester)

        # Default parameters, all submissions this semester, as would be shown in staff "Approved" tab
        all_approved = QuestSubmission.objects.all_approved()
        self.assertQuerySetEqual(
            all_approved,
            [sub_approved, sub_approved_no_xp, sub_approved_different_quest, sub_approved_user],
            ordered=False
        )

        # active_semester_only=False should include sub_approved_other_semester
        all_approved = QuestSubmission.objects.all_approved(active_semester_only=False)
        self.assertQuerySetEqual(
            all_approved,
            [sub_approved, sub_approved_different_quest, sub_approved_other_semester, sub_approved_no_xp, sub_approved_user],
            ordered=False
        )

        # quest=quest should not include sub_approved_different_quest
        all_approved = QuestSubmission.objects.all_approved(quest=quest)
        self.assertQuerySetEqual(
            all_approved,
            [sub_approved, sub_approved_no_xp, sub_approved_user],
            ordered=False
        )

        # user=test_user should only include sub_approved_user
        all_approved = QuestSubmission.objects.all_approved(user=user)
        self.assertQuerySetEqual(
            all_approved,
            [sub_approved_user],
            ordered=False
        )


class SubmissionTestModel(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a semester, teacher, student, and a base submission shared across the tests."""
        cls.semester = baker.make(Semester)
        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)
        cls.submission = baker.make(QuestSubmission, quest__name="Test")

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_submission__creation_and_quest_name(self):
        """Creating a QuestSubmission yields a QuestSubmission linked to its quest."""
        self.assertIsInstance(self.submission, QuestSubmission)
        self.assertEqual("Test", self.submission.quest.name)

    def test_get_absolute_url__submission_page_loads(self):
        """The submission's absolute URL is reachable and returns 200."""
        self.assertEqual(self.client.get(self.submission.get_absolute_url(), follow=True).status_code, 200)

    def test_mark_completed__sets_state_and_clears_draft(self):
        """mark_completed sets completion state, records the submission time, and clears the draft comment."""
        user = baker.make(User)
        sub = baker.make(QuestSubmission, user=user)
        draft_comment = Comment.objects.create_comment(
            user=self.student,
            text="draft comment",
            target=sub,
            path=sub.get_absolute_url(),
        )
        sub.draft_comment = draft_comment
        sub.save()

        self.assertFalse(sub.is_completed)
        self.assertEqual(sub.draft_comment, draft_comment)
        self.assertIsNone(user.profile.time_of_last_submission)
        sub.mark_completed()
        self.assertEqual(user.profile.time_of_last_submission, sub.time_completed)
        self.assertTrue(sub.is_completed)
        self.assertIsNotNone(sub.first_time_completed)
        self.assertIsNone(sub.draft_comment)

    def test_get_previous__returns_prior_submission(self):
        """ If this is a repeatable quest and has been completed already, return that previous submission """
        repeat_quest = baker.make(Quest, name="repeatable-quest", max_repeats=-1)
        first_sub = baker.make(QuestSubmission, user=self.student, quest=repeat_quest, semester=self.semester)
        self.assertIsNone(first_sub.get_previous())
        # need to complete so can make another
        first_sub.mark_completed()
        SiteConfig.get().set_active_semester(first_sub.semester.id)
        second_sub = QuestSubmission.objects.create_submission(user=self.student, quest=repeat_quest)
        self.assertEqual(first_sub, second_sub.get_previous())

    def test_get_previous__fixes_duplicate_ordinals(self):
        """Submissions that have the same ordinals will be automatically fixed"""
        repeat_quest = baker.make(Quest, name="repeatable-quest", max_repeats=-1)
        first_sub = baker.make(QuestSubmission, user=self.student, quest=repeat_quest, semester=self.semester)
        self.assertIsNone(first_sub.get_previous())
        self.assertEqual(first_sub.ordinal, 1)
        # need to complete so can make another
        first_sub.mark_completed()
        SiteConfig.get().set_active_semester(first_sub.semester.id)
        second_sub = QuestSubmission.objects.create_submission(user=self.student, quest=repeat_quest)
        self.assertEqual(second_sub.ordinal, 2)
        second_sub.mark_completed()

        self.assertEqual(first_sub, second_sub.get_previous())

        third_sub = QuestSubmission.objects.create_submission(user=self.student, quest=repeat_quest)
        self.assertEqual(third_sub.ordinal, 3)
        third_sub.mark_completed()

        fourth_sub = QuestSubmission.objects.create_submission(user=self.student, quest=repeat_quest)
        self.assertEqual(fourth_sub.ordinal, 4)
        fourth_sub.mark_completed()

        # Make the 3rd submission's ordinal same with the second
        old_third_submission_ordinal = third_sub.ordinal
        third_sub.ordinal = second_sub.ordinal
        third_sub.save()

        # Assert that MultipleObjectsReturned is raised now since we now have 2 records with the same ordinal
        with self.assertRaises(QuestSubmission.MultipleObjectsReturned):
            QuestSubmission.objects.get(quest=repeat_quest, user=self.student, ordinal=second_sub.ordinal)

        fourth_sub.ordinal = old_third_submission_ordinal
        fourth_sub.save()

        self.assertEqual(second_sub.ordinal, third_sub.ordinal)

        # Mock fhe _fix_ordinal so we can test that it was called.
        # See SO solution: https://stackoverflow.com/a/50970342
        fourth_sub._fix_ordinal = MagicMock(side_effect=fourth_sub._fix_ordinal)

        # This should fix the ordinals
        self.assertEqual(fourth_sub.get_previous(), QuestSubmission.objects.get(pk=third_sub.pk))
        self.assertTrue(fourth_sub._fix_ordinal.called)
        self.assertEqual(fourth_sub._fix_ordinal.call_count, 1)

        third_sub.refresh_from_db()
        self.assertEqual(third_sub.ordinal, old_third_submission_ordinal)

    def test_get_minutes_to_complete__returns_minutes_between_timestamps(self):
        """Completed quests should return the difference between the timestamp (creation) and time completed, in minutes."""
        minutes = 5
        time_delta = datetime.timedelta(0, minutes * 60)
        # print(time_delta.total_seconds())
        self.submission.mark_completed()

        # fake the completion time
        self.submission.first_time_completed = self.submission.timestamp + time_delta
        self.assertEqual(self.submission.get_minutes_to_complete(), minutes)

        #  if quest is returned and resubmitted, should still give same time:
        self.submission.mark_returned()
        self.submission.mark_completed()
        self.assertEqual(self.submission.get_minutes_to_complete(), minutes)

    def test_get_minutes_to_complete__none_if_not_completed(self):
        """Return None if the submission has not been completed yet."""
        # the setup submission should not be completed yet, but make sure
        self.assertFalse(self.submission.is_completed, False)
        self.assertIsNone(self.submission.get_minutes_to_complete())


class QuestExpiredAnnotationTest(ByteDeckTenantTestCase):
    """Quest.expired() is called for every quest rendered in list templates, so
    it reuses an ``is_expired`` annotation from the queryset when one is present
    instead of issuing a query per call."""

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_expired__prefers_is_expired_annotation(self):
        """When the instance carries an is_expired annotation, expired() returns
        it without issuing a query."""
        quest = baker.make(Quest)

        quest.is_expired = True  # simulate the queryset annotation
        with self.assertNumQueries(0):
            self.assertTrue(quest.expired())

        quest.is_expired = False
        with self.assertNumQueries(0):
            self.assertFalse(quest.expired())

    def test_expired__falls_back_to_query_without_annotation(self):
        """Without the annotation, expired() still computes the value from the DB;
        a quest with no expiry date has not expired."""
        quest = baker.make(Quest, date_expired=None)
        self.assertFalse(quest.expired())


class QuestManagerPrefetchTest(ByteDeckTenantTestCase):
    """The Drafts and Archived staff tabs render the same template rows as the
    'Available' tab, which reads each quest's campaign, editor profile and tags.
    all_drafts() and all_archived() must prefetch those relations so a page of
    quests does not issue a query per row."""

    @classmethod
    def setUpTestData(cls):
        """Create a teacher (staff caller and quest editor) and a campaign shared across the tests."""
        # a teacher is needed both as staff caller and as each quest's editor
        cls.teacher = User.objects.create_user('teacher', is_staff=True)
        cls.campaign = baker.make(Category, title="Test Campaign")

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def _make_quests(self, **kwargs):
        """Create three quests with a campaign, editor and tags set, so the
        related-object accessors exercised by the template have data to read."""
        quests = []
        for i in range(3):
            quest = baker.make(Quest, campaign=self.campaign, editor=self.teacher, **kwargs)
            quest.tags.add(f'tag-{i}')
            quests.append(quest)
        return quests

    def test_all_drafts__prefetches_related_objects(self):
        """all_drafts() prefetches campaign, editor profile and tags, so reading
        them for every draft quest issues no additional queries."""
        self._make_quests(published=False)

        drafts = list(Quest.objects.all_drafts(self.teacher))
        self.assertEqual(len(drafts), 3)

        with self.assertNumQueries(0):
            for quest in drafts:
                self.assertEqual(quest.campaign.title, "Test Campaign")
                # editor__profile is select_related; profile is the reverse 1-1
                self.assertIsNotNone(quest.editor.profile)
                self.assertEqual(len(quest.tags.all()), 1)

    def test_all_archived__prefetches_related_objects(self):
        """all_archived() prefetches campaign, editor profile and tags, so reading
        them for every archived quest issues no additional queries."""
        self._make_quests(archived=True)

        archived = list(Quest.objects.all_archived(self.teacher))
        self.assertEqual(len(archived), 3)

        with self.assertNumQueries(0):
            for quest in archived:
                self.assertEqual(quest.campaign.title, "Test Campaign")
                self.assertIsNotNone(quest.editor.profile)
                self.assertEqual(len(quest.tags.all()), 1)
