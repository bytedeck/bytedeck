import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
from model_mommy.recipe import Recipe

from notifications.models import Notification


class NotificationTestModel(TestCase):

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = mommy.make(User)
        self.notification = mommy.make(Notification)
        # self.assertion = mommy.make(BadgeAssertion)
        # self.badge = Recipe(Badge, xp=20).make()
        # self.badge_assertion_recipe = Recipe(BadgeAssertion, user=self.student, badge=self.badge)

    def test_notification_creation(self):
        self.assertIsInstance(self.notification, Notification)
        self.assertIsNotNone(str(self.notification))

        # print(str(self.notification))
    #
    # def test_badge_assertion_url(self):
    #     self.assertEqual(self.client.get(self.assertion.get_absolute_url(), follow=True).status_code, 200)
    #
    # def test_badge_assertion_count(self):
    #     num = randint(1, 9)
    #     for _ in range(num):
    #         badge_assertion = BadgeAssertion.objects.create_assertion(
    #             self.student,
    #             self.badge
    #         )
    #         # Why doesn't below work?
    #         #badge_assertion = self.badge_assertion_recipe.make()
    #     count = badge_assertion.count()
    #     # print(num, count)
    #     self.assertEqual(num, count)
    #
    # def test_badge_assertion_count_bootstrap_badge(self):
    #     """Returns empty string if count < 2, else returns proper count"""
    #     badge_assertion = mommy.make(BadgeAssertion)
    #     self.assertEqual(badge_assertion.count_bootstrap_badge(), "")
    #
    #     num = randint(1, 9)
    #     for _ in range(num):
    #         badge_assertion = BadgeAssertion.objects.create_assertion(
    #             self.student,
    #             self.badge
    #         )
    #         # Why doesn't below work?
    #         #badge_assertion = self.badge_assertion_recipe.make()
    #     count = badge_assertion.count_bootstrap_badge()
    #     # print(num, count)
    #     self.assertEqual(num, count)
    #
    # def test_badge_assertion_get_duplicate_assertions(self):
    #     num = randint(1, 9)
    #     values = []
    #     for _ in range(num):
    #         badge_assertion = self.badge_assertion_recipe.make()
    #         values.append(repr(badge_assertion))
    #
    #     qs = badge_assertion.get_duplicate_assertions()
    #     self.assertQuerysetEqual(list(qs), values,)
    #
    # def test_badge_assertion_manager_create_assertion(self):
    #     new_assertion = BadgeAssertion.objects.create_assertion(
    #         self.student,
    #         mommy.make(Badge)
    #     )
    #     self.assertIsInstance(new_assertion, BadgeAssertion)
    #
    # def test_badge_assertion_manager_xp_to_date(self):
    #     xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
    #     self.assertEqual(xp, 0)
    #
    #     # give them a badge assertion and make sure the XP works
    #     BadgeAssertion.objects.create_assertion(
    #         self.student,
    #         self.badge
    #     )
    #     xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
    #     self.assertEqual(xp, self.badge.xp)
    #
    # def test_badge_assertion_manager_get_by_type_for_user(self):
    #     badge_list_by_type = BadgeAssertion.objects.get_by_type_for_user(self.student)
    #     self.assertIsInstance(badge_list_by_type, list)
    #     # TODO need to test this properly
    #
    # def test_badge_assertion_manager_check_for_new_assertions(self):
    #     BadgeAssertion.objects.check_for_new_assertions(self.student)
    #     # TODO need to test this properly
