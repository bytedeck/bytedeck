import re

from datetime import timedelta
from django.utils.timezone import localtime
from django.contrib.auth import get_user_model

from model_bakery import baker
from model_bakery.recipe import Recipe
from freezegun import freeze_time
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from siteconfig.models import SiteConfig

from quest_manager.models import Category, CommonData, Quest, QuestSubmission
from courses.models import Semester


class CategoryTestModel(TenantTestCase):  # aka Campaigns
    def setUp(self):
        self.category = baker.make(Category)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.category, Category)
        self.assertEqual(str(self.category), self.category.title)


class CommonDataTestModel(TenantTestCase):
    def setUp(self):
        self.common_data = baker.make(CommonData)

    def test_badge_series_creation(self):
        self.assertIsInstance(self.common_data, CommonData)
        self.assertEqual(str(self.common_data), self.common_data.title)


class QuestTestModel(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.quest = baker.make(Quest)

    def test_badge_creation(self):
        self.assertIsInstance(self.quest, Quest)
        self.assertEqual(str(self.quest), self.quest.name)

    def test_quest_icon(self):
        pass

    def test_quest_url(self):
        self.assertEqual(self.client.get(self.quest.get_absolute_url(), follow=True).status_code, 200)

    def test_quest_html_formatting(self):
        test_markup = "<p>this <span>span</span> tag should not break</p>"
        self.quest.instructions = test_markup
        # Auto formatting on save
        self.quest.save()
        formatted_markup = self.quest.instructions

        # search for line breaks before or after span tags
        matches_found = re.search('(([ ]+)?\n([ ]+)?</?span>)|(</?span>([ ]+)?\n([ ]+)?)', formatted_markup)
        self.assertIsNone(matches_found)

    def test_quest_html_formatting_math(self):
        test_markup = r"""<span class="note-math"><span class="katex"><span class="katex-mathml"><math><semantics><mrow><mrow><mi>x</mi></mrow></mrow><annotation encoding="application/x-tex">{x}</annotation></semantics></math></span>""" # noqa
        self.quest.instructions = test_markup
        # Auto formatting on save
        self.quest.save()
        formatted_markup = self.quest.instructions

        self.assertIn(test_markup, formatted_markup)

        matches_found = re.search('({{)|(}})', formatted_markup)
        self.assertIsNone(matches_found)

    def test_quest_html_formatting_tabs(self):
        markup = [  # test, expected out come
            ("<p>some text</p>", "<p>\n    some text\n</p>"),
            ("<p>some text\n\n</p>", "<p>\n    some text\n</p>"),
            ("<p>some \ntext</p>", "<p>\n    some \ntext\n</p>"),
            ("<p>some \n text</p>", "<p>\n    some \n    text\n</p>"),
            ("<ol><li>test</li></ol>", "<ol>\n    <li>\n        test\n    </li>\n</ol>"),
            (" <p>", "<p>\n</p>")
        ]
        for pair in markup:
            self.quest.instructions = pair[0]
            # Auto formatting on save
            self.quest.save()
            formatted_markup = self.quest.instructions
            self.assertEqual(formatted_markup, pair[1])

    @freeze_time('2018-10-12 00:54:00', tz_offset=0)
    def test_is_repeat_available(self):
        """
        QuestManager.is_repeat_available should return True if:
            1. it is repeatable (is_repeatable != 0)
            2. the cooldown time has passed for the quest since the last completion
            3. the max repeats have not been completed already (by semester or overall)

        Assumes there has already been at least one submission (change that?)

        def test_is_repeat_available(self, user):"""

        User = get_user_model()
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
        with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
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
        new_active_sem = baker.make(Semester, active=True)
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


class SubmissionTestModel(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()
        self.semester = baker.make(Semester)
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)
        self.submission = baker.make(QuestSubmission, quest__name="Test")
        # self.badge = Recipe(Badge, xp=20).make()

        # self.badge_assertion_recipe = Recipe(QuestSubmission, user=self.student, badge=self.badge)

    def test_submission_creation(self):
        self.assertIsInstance(self.submission, QuestSubmission)
        self.assertEqual(str("Test"), self.submission.quest.name)

    def test_submission_url(self):
        self.assertEqual(self.client.get(self.submission.get_absolute_url(), follow=True).status_code, 200)

    def test_submission_without_quest(self):
        # creating a submission without a quest, null=True so no Quest created.
        sub = baker.make(QuestSubmission)
        self.assertIsNone(sub.quest)
        self.assertIsNotNone(str(sub))

    def test_submission_mark_completed(self):
        draft_text = "Draft words"
        sub = baker.make(QuestSubmission, draft_text=draft_text)
        self.assertFalse(sub.is_completed)
        self.assertEqual(sub.draft_text, draft_text)
        sub.mark_completed()
        self.assertTrue(sub.is_completed)
        self.assertIsNotNone(sub.first_time_completed)
        self.assertIsNone(sub.draft_text)

    def test_submission_get_previous(self):
        """ If this is a repeatable quest and has been completed already, return that previous submission """
        repeat_quest = baker.make(Quest, name="repeatable-quest", max_repeats=-1)
        first_sub = baker.make(QuestSubmission, user=self.student, quest=repeat_quest, semester=self.semester)
        self.assertIsNone(first_sub.get_previous())
        # need to complete so can make another
        first_sub.mark_completed()
        SiteConfig.get().set_active_semester(first_sub.semester.id)
        second_sub = QuestSubmission.objects.create_submission(user=self.student, quest=repeat_quest)
        self.assertEqual(first_sub, second_sub.get_previous())
