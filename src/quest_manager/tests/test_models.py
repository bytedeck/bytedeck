import re

import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
from model_mommy.recipe import Recipe

from quest_manager.models import Category, CommonData, Quest, QuestSubmission


class CategoryTestModel(TestCase):  # aka Campaigns
    def setUp(self):
        self.category = mommy.make(Category)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.category, Category)
        self.assertEqual(str(self.category), self.category.title)


class CommonDataTestModel(TestCase):
    def setUp(self):
        self.common_data = mommy.make(CommonData)

    def test_badge_series_creation(self):
        self.assertIsInstance(self.common_data, CommonData)
        self.assertEqual(str(self.common_data), self.common_data.title)


class QuestTestModel(TestCase):

    def setUp(self):
        self.quest = mommy.make(Quest)

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


class SubmissionTestModel(TestCase):

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = mommy.make(User)
        self.submission = mommy.make(QuestSubmission, quest__name="Test")
        # self.badge = Recipe(Badge, xp=20).make()

        # self.badge_assertion_recipe = Recipe(QuestSubmission, user=self.student, badge=self.badge)

    def test_submission_creation(self):
        self.assertIsInstance(self.submission, QuestSubmission)
        self.assertEqual(str("Test"), self.submission.quest.name)

    def test_submission_url(self):
        self.assertEqual(self.client.get(self.submission.get_absolute_url(), follow=True).status_code, 200)

    def test_submission_without_quest(self):
        # creating a submission without a quest, null=True so no Quest created.
        sub = mommy.make(QuestSubmission)
        self.assertIsNone(sub.quest)
        self.assertIsNotNone(str(sub))

    def test_submission_mark_completed(self):
        draft_text = "Draft words"
        sub = mommy.make(QuestSubmission, draft_text=draft_text)
        self.assertFalse(sub.is_completed)
        self.assertEqual(sub.draft_text, draft_text)
        sub.mark_completed()
        self.assertTrue(sub.is_completed)
        self.assertIsNotNone(sub.first_time_completed)
        self.assertIsNone(sub.draft_text)

#
#     def test_badge_assertion_count(self):
#         num = randint(1, 9)
#         for _ in range(num):
#             badge_assertion = BadgeAssertion.objects.create_assertion(
#                 self.student,
#                 self.badge
#             )
#             # Why doesn't below work?
#             #badge_assertion = self.badge_assertion_recipe.make()
#         count = badge_assertion.count()
#         # print(num, count)
#         self.assertEqual(num, count)
#
#     def test_badge_assertion_count_bootstrap_badge(self):
#         """Returns empty string if count < 2, else returns proper count"""
#         badge_assertion = mommy.make(BadgeAssertion)
#         self.assertEqual(badge_assertion.count_bootstrap_badge(), "")
#
#         num = randint(1, 9)
#         for _ in range(num):
#             badge_assertion = BadgeAssertion.objects.create_assertion(
#                 self.student,
#                 self.badge
#             )
#             # Why doesn't below work?
#             #badge_assertion = self.badge_assertion_recipe.make()
#         count = badge_assertion.count_bootstrap_badge()
#         # print(num, count)
#         self.assertEqual(num, count)
#
#     def test_badge_assertion_get_duplicate_assertions(self):
#         num = randint(1, 9)
#         values = []
#         for _ in range(num):
#             badge_assertion = self.badge_assertion_recipe.make()
#             values.append(repr(badge_assertion))
#
#         qs = badge_assertion.get_duplicate_assertions()
#         self.assertQuerysetEqual(list(qs), values,)
#
#     def test_badge_assertion_manager_create_assertion(self):
#         new_assertion = BadgeAssertion.objects.create_assertion(
#             self.student,
#             mommy.make(Badge)
#         )
#         self.assertIsInstance(new_assertion, BadgeAssertion)
#
#     def test_badge_assertion_manager_xp_to_date(self):
#         xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
#         self.assertEqual(xp, 0)
#
#         # give them a badge assertion and make sure the XP works
#         BadgeAssertion.objects.create_assertion(
#             self.student,
#             self.badge
#         )
#         xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
#         self.assertEqual(xp, self.badge.xp)
#
#     def test_badge_assertion_manager_get_by_type_for_user(self):
#         badge_list_by_type = BadgeAssertion.objects.get_by_type_for_user(self.student)
#         self.assertIsInstance(badge_list_by_type, list)
#         # TODO need to test this properly
#
#     def test_badge_assertion_manager_check_for_new_assertions(self):
#         BadgeAssertion.objects.check_for_new_assertions(self.student)
#         # TODO need to test this properly
#
#
#
