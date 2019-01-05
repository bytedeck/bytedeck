from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
from model_mommy.recipe import Recipe

from badges.models import Badge, BadgeAssertion, BadgeType, BadgeSeries


class BadgeTypeTestModel(TestCase):
    def setUp(self):
        self.badge_type = mommy.make(BadgeType)

    def test_badge_creation(self):
        self.assertIsInstance(self.badge_type, BadgeType)
        self.assertEqual(str(self.badge_type), self.badge_type.name)


class BadgeSeriesTestModel(TestCase):
    def setUp(self):
        self.badge_series = mommy.make(BadgeSeries)

    def test_badge_creation(self):
        self.assertIsInstance(self.badge_series, BadgeSeries)
        self.assertEqual(str(self.badge_series), self.badge_series.name)


class BadgeTestModel(TestCase):

    def setUp(self):
        self.badge = mommy.make(Badge)

    def test_badge_creation(self):
        self.assertIsInstance(self.badge, Badge)
        self.assertEqual(str(self.badge), self.badge.name)


class BadgeAssertionTestModel(TestCase):

    def setUp(self):
        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.assertion = mommy.make(BadgeAssertion)

    def test_badge_assertion_creation(self):
        self.assertIsInstance(self.assertion, BadgeAssertion)
        self.assertEqual(str(self.assertion), self.assertion.badge.name)
