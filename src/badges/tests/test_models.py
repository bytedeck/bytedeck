import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from model_mommy import mommy
from model_mommy.recipe import Recipe

from badges.models import Badge, BadgeAssertion, BadgeType, BadgeSeries, BadgeRarity

User = get_user_model()


class BadgeRarityTestModel(TestCase):
    def setUp(self):
        self.common = mommy.make(BadgeRarity)

    def test_badge_rarity_creation(self):
        self.assertIsInstance(self.common, BadgeRarity)
        self.assertEqual(str(self.common), self.common.name)

    def test_get_rarity(self):
        self.common = mommy.make(BadgeRarity, percentile=100.0)
        self.rare = mommy.make(BadgeRarity, percentile=50.0)
        self.ultrarare = mommy.make(BadgeRarity, percentile=1.0)

        self.assertEqual(BadgeRarity.objects.get_rarity(0.5), self.ultrarare)
        self.assertEqual(BadgeRarity.objects.get_rarity(49.0), self.rare)
        self.assertEqual(BadgeRarity.objects.get_rarity(50.0), self.rare)
        self.assertEqual(BadgeRarity.objects.get_rarity(100.0), self.common)
        self.assertEqual(BadgeRarity.objects.get_rarity(110.0), self.common)


class BadgeTypeTestModel(TestCase):
    def setUp(self):
        self.badge_type = mommy.make(BadgeType)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.badge_type, BadgeType)
        self.assertEqual(str(self.badge_type), self.badge_type.name)


class BadgeSeriesTestModel(TestCase):
    def setUp(self):
        self.badge_series = mommy.make(BadgeSeries)

    def test_badge_series_creation(self):
        self.assertIsInstance(self.badge_series, BadgeSeries)
        self.assertEqual(str(self.badge_series), self.badge_series.name)


class BadgeTestModel(TestCase):

    def setUp(self):
        self.badge = mommy.make(Badge)

    def test_badge_creation(self):
        self.assertIsInstance(self.badge, Badge)
        self.assertEqual(str(self.badge), self.badge.name)

    def test_badge_icon(self):
        pass

    def test_badge_url(self):
        self.assertEqual(self.client.get(self.badge.get_absolute_url(), follow=True).status_code, 200)


class BadgeAssertionTestModel(TestCase):

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        # needed because BadgeAssertions use a default that might not exist yet
        self.sem = mommy.make('courses.semester', pk=djconfig.config.hs_active_semester)

        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = mommy.make(User)
        self.assertion = mommy.make(BadgeAssertion, semester=self.sem)
        self.badge = Recipe(Badge, xp=20).make()

        self.badge_assertion_recipe = Recipe(BadgeAssertion, user=self.student, badge=self.badge, semester=self.sem)

    def test_badge_assertion_creation(self):
        self.assertIsInstance(self.assertion, BadgeAssertion)
        self.assertEqual(str(self.assertion), self.assertion.badge.name)

    def test_badge_assertion_url(self):
        self.assertEqual(self.client.get(self.assertion.get_absolute_url(), follow=True).status_code, 200)

    def test_badge_assertion_count(self):
        num = 5
        for _ in range(num):
            badge_assertion = BadgeAssertion.objects.create_assertion(
                self.student,
                self.badge,
                issued_by=self.teacher
            )

        # Why doesn't below work?
        # badge_assertion = self.badge_assertion_recipe.make()
        count = badge_assertion.count()
        # print(num, count)
        self.assertEqual(num, count)

    def test_badge_assertion_count_bootstrap_badge(self):
        """Returns empty string if count < 2, else returns proper count"""
        badge_assertion = mommy.make(BadgeAssertion, semester=self.sem)
        self.assertEqual(badge_assertion.count_bootstrap_badge(), "")

        num = 4
        for _ in range(num):
            badge_assertion = BadgeAssertion.objects.create_assertion(
                self.student,
                self.badge,
                issued_by=self.teacher
            )
            # Why doesn't below work?
            # badge_assertion = self.badge_assertion_recipe.make()
        count = badge_assertion.count_bootstrap_badge()
        # print(num, count)
        self.assertEqual(num, count)

    def test_badge_assertion_get_duplicate_assertions(self):
        num = 5
        values = []
        for _ in range(num):
            badge_assertion = self.badge_assertion_recipe.make()
            values.append(repr(badge_assertion))

        qs = badge_assertion.get_duplicate_assertions()
        self.assertQuerysetEqual(list(qs), values,)

    def test_badge_assertion_manager_create_assertion(self):
        new_assertion = BadgeAssertion.objects.create_assertion(
            self.student,
            mommy.make(Badge),
            self.teacher
        )
        self.assertIsInstance(new_assertion, BadgeAssertion)

    def test_badge_assertion_manager_xp_to_date(self):
        xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
        self.assertEqual(xp, 0)

        # give them a badge assertion and make sure the XP works
        BadgeAssertion.objects.create_assertion(
            self.student,
            self.badge,
            self.teacher
        )
        xp = BadgeAssertion.objects.calculate_xp_to_date(self.student, timezone.now())
        self.assertEqual(xp, self.badge.xp)

    def test_badge_assertion_manager_get_by_type_for_user(self):
        badge_list_by_type = BadgeAssertion.objects.get_by_type_for_user(self.student)
        self.assertIsInstance(badge_list_by_type, list)
        # TODO need to test this properly

    def test_badge_assertion_manager_check_for_new_assertions(self):
        BadgeAssertion.objects.check_for_new_assertions(self.student)
        # TODO need to test this properly

    def test_fraction_of_active_users_granted_this(self):
        num_students_with_badge = 3

        students_with_badge = mommy.make(User, _quantity=num_students_with_badge)
        self.assertEqual(len(students_with_badge), num_students_with_badge)

        total_students = User.objects.filter(is_active=True).count()

        badge = mommy.make(Badge)

        for student in students_with_badge:
            mommy.make(BadgeAssertion, user=student, badge=badge)

        fraction = badge.fraction_of_active_users_granted_this()
        self.assertEqual(fraction, num_students_with_badge / total_students)

        percentile = badge.percent_of_active_users_granted_this()
        self.assertEqual(percentile, num_students_with_badge / total_students * 100)
