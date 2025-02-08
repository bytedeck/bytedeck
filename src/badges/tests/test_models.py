from unittest import mock
from django.contrib.auth import get_user_model
from django.utils import timezone

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker
from model_bakery.recipe import Recipe

from badges.models import Badge, BadgeAssertion, BadgeRarity, BadgeSeries, BadgeType
from siteconfig.models import SiteConfig
from notifications.models import Notification

User = get_user_model()


class BadgeRarityModelTest(TenantTestCase):
    def setUp(self):
        # clear default mark range variables
        BadgeRarity.objects.all().delete()
        self.common = baker.make(BadgeRarity, percentile=90.0)
        self.rare = baker.make(BadgeRarity, percentile=80.0)
        self.ultrarare = baker.make(BadgeRarity, percentile=70.0)

    def test_badge_rarity_creation(self):
        self.assertIsInstance(self.common, BadgeRarity)
        self.assertEqual(str(self.common), self.common.name)

    def test_get_rarity(self):

        self.assertEqual(BadgeRarity.objects.get_rarity(69.0), self.ultrarare)
        self.assertEqual(BadgeRarity.objects.get_rarity(79.0), self.rare)
        self.assertEqual(BadgeRarity.objects.get_rarity(80.0), self.rare)
        self.assertEqual(BadgeRarity.objects.get_rarity(90.0), self.common)
        self.assertEqual(BadgeRarity.objects.get_rarity(91), None)

        ubercommon = baker.make(BadgeRarity, percentile=100.0)
        self.assertEqual(BadgeRarity.objects.get_rarity(100), ubercommon)
        # >100 is considered 100 for the purposes of rarity
        self.assertEqual(BadgeRarity.objects.get_rarity(110), ubercommon)


class BadgeTypeModelTest(TenantTestCase):
    def setUp(self):
        self.badge_type = baker.make(BadgeType)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.badge_type, BadgeType)
        self.assertEqual(str(self.badge_type), self.badge_type.name)

    def test_model_protection(self):
        """ Badge types shouldn't be deleted if they have any assigned badges """

        # make sure initial variables are in place
        badge = baker.make(Badge, xp=5, badge_type=self.badge_type)
        self.assertTrue(Badge.objects.count(), 1)
        self.assertEqual(badge.badge_type, self.badge_type)

        # see if models.PROTECT is in place
        self.assertRaises(Exception, self.badge_type.delete)


class BadgeSeriesTestModel(TenantTestCase):
    def setUp(self):
        self.badge_series = baker.make(BadgeSeries)

    def test_badge_series_creation(self):
        self.assertIsInstance(self.badge_series, BadgeSeries)
        self.assertEqual(str(self.badge_series), self.badge_series.name)


class BadgeTestModel(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.badge = baker.make(Badge)

    def test_badge_creation(self):
        self.assertIsInstance(self.badge, Badge)
        self.assertEqual(str(self.badge), self.badge.name)

    def test_get_icon_url(self):
        """If the badge has an icon, return its url, otherwise return default icon url from SiteConfig"""

        # doesn't have an icon, should return default
        self.assertEqual(self.badge.get_icon_url(), SiteConfig.get().get_default_icon_url())

        # give it an icon
        self.badge.icon = "test_icon.png"
        self.badge.full_clean()
        self.badge.save()
        self.assertEqual(self.badge.get_icon_url(), self.badge.icon.url)

    def test_badge_url(self):
        self.assertEqual(self.client.get(self.badge.get_absolute_url(), follow=True).status_code, 200)

    @mock.patch('badges.models.BadgeRarity.objects.get_rarity')
    def test_get_rarity_icon__without_rarity(self, mock_get_rarity):
        mock_get_rarity.return_value = None

        result = self.badge.get_rarity_icon()

        mock_get_rarity.assert_called_once()
        self.assertEqual(result, '')

    @mock.patch('badges.models.BadgeRarity.objects.get_rarity')
    @mock.patch('badges.models.Badge.percent_of_active_users_granted_this')
    def test_get_rarity_icon__with_rarity(self, mock_percentile, mock_get_rarity):
        mock_percentile.return_value = 80  # Set the desired percentile value
        mock_badge_rarity = mock.Mock()
        mock_badge_rarity.get_icon_html.return_value = '<span class="badge-icon">Icon</span>'
        mock_get_rarity.return_value = mock_badge_rarity

        result = self.badge.get_rarity_icon()

        mock_percentile.assert_called_once()
        mock_get_rarity.assert_called_once_with(80)  # Verify the correct percentile is passed
        mock_badge_rarity.get_icon_html.assert_called_once()
        self.assertEqual(result, '<span class="badge-icon">Icon</span>')


class BadgeAssertionManagerTest(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)
        # self.assertion = baker.make(BadgeAssertion, semester=self.sem)
        # self.badge = Recipe(Badge, xp=20).make()

        # self.badge_assertion_recipe = Recipe(BadgeAssertion, user=self.student, badge=self.badge, semester=self.sem)

    def test_user_badge_assertion_count(self):
        """Test that BadgeAssertion.objects.user_assertion_count_of_badge() returns a User queryset with
        the correct number of assertions for each user as an "assertion_count" annotation on the queryset"""

        badge = baker.make(Badge, name="badge1")
        user2 = baker.make(User)
        user3 = baker.make(User)

        baker.make(BadgeAssertion, user=self.student, badge=badge, _quantity=3)
        baker.make(BadgeAssertion, user=user2, badge=badge, _quantity=1)

        qs = BadgeAssertion.objects.user_badge_assertion_count(badge)

        self.assertEqual(qs.count(), 2)  # user3 has no assertions so not included
        self.assertEqual(qs.get(id=self.student.id).assertion_count, 3)
        self.assertEqual(qs.get(id=user2.id).assertion_count, 1)
        self.assertNotIn(user3, qs)

    def test_all_for_user_distinct(self):
        """
        BadgeAssertion.objects.all_for_user_distinct() returns a queryset of BadgeAssertions assigned to a user
        that are distinct by badge, and sorted by badge.badge_type.sort_order, badge.sort_order

        Badge objects without a defined sort_order value should default to sort_order = 0
        """

        # create badges to assign to user
        badge1 = baker.make(Badge, name='Badge 0')  # sort order should default to 0 when not set
        badge2 = baker.make(Badge, name='Badge 1', sort_order=1)
        badge3 = baker.make(Badge, name='Badge 2', sort_order=2)

        # give the student two of badge1
        badge_assertion = baker.make(BadgeAssertion, user=self.student, badge=badge1)
        baker.make(BadgeAssertion, user=self.student, badge=badge1)  # should not be returned by all_for_user_distinct so not stored in a variable

        # one of badge2
        badge_assertion2 = baker.make(BadgeAssertion, user=self.student, badge=badge2)

        # and one of badge3
        badge_assertion3 = baker.make(BadgeAssertion, user=self.student, badge=badge3)

        # this should only return three, not the duplicate badge_assertion of badge1
        # and they should be sorted by badge.sort_order
        qs = BadgeAssertion.objects.all_for_user_distinct(user=self.student)
        self.assertQuerysetEqual(qs, [badge_assertion, badge_assertion2, badge_assertion3])

    def test_all_for_user_distinct__badge_type_order_correct(self):
        """
        This test is the same with test_all_for_user_distinct, except that this test checks
        that the badges are sorted by badge_type.sort_order, badge.sort_order.
        """

        # create badges to assign to user but with badge_type in reverse order
        badge1 = baker.make(Badge, name='Badge 0', badge_type__sort_order=2)
        badge2 = baker.make(Badge, name='Badge 1', badge_type__sort_order=1, sort_order=1)
        badge3 = baker.make(Badge, name='Badge 2', badge_type__sort_order=0, sort_order=2)

        # give the student two of badge1
        badge_assertion = baker.make(BadgeAssertion, user=self.student, badge=badge1)
        baker.make(BadgeAssertion, user=self.student, badge=badge1)  # should not be returned by all_for_user_distinct so not stored in a variable

        # one of badge2
        badge_assertion2 = baker.make(BadgeAssertion, user=self.student, badge=badge2)

        # and one of badge3
        badge_assertion3 = baker.make(BadgeAssertion, user=self.student, badge=badge3)

        qs = BadgeAssertion.objects.all_for_user_distinct(user=self.student)
        self.assertQuerysetEqual(qs, [badge_assertion3, badge_assertion2, badge_assertion])


class BadgeAssertionTestModel(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)
        self.assertion = baker.make(BadgeAssertion, semester=self.sem)
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
        badge_assertion = baker.make(BadgeAssertion, semester=self.sem)
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
            values.append(badge_assertion)

        qs = badge_assertion.get_duplicate_assertions()
        self.assertQuerysetEqual(list(qs), values, )

    def test_badge_assertion_manager_create_assertion(self):

        # no semester
        new_assertion = BadgeAssertion.objects.create_assertion(
            self.student,
            baker.make(Badge),
            self.teacher
        )
        self.assertIsInstance(new_assertion, BadgeAssertion)

        # no teacher
        new_assertion = BadgeAssertion.objects.create_assertion(
            self.student,
            baker.make(Badge),
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
        # TODO need to tefrom django.contrib.auth import get_user_model

    def test_fraction_of_active_users_granted_this(self):
        num_students_with_badge = 3

        students_with_badge = baker.make(User, _quantity=num_students_with_badge)
        self.assertEqual(len(students_with_badge), num_students_with_badge)

        total_students = User.objects.filter(is_active=True).count()

        badge = baker.make(Badge)

        for student in students_with_badge:
            baker.make(BadgeAssertion, user=student, badge=badge)

        fraction = badge.fraction_of_active_users_granted_this()
        self.assertEqual(fraction, num_students_with_badge / total_students)

        percentile = badge.percent_of_active_users_granted_this()
        self.assertEqual(percentile, num_students_with_badge / total_students * 100)

    def test_post_save_receiver__creates_notifications(self):
        """" Checks to see if BadeAssertion's post_save_receiver generates notifications
        Creates 3 badge assertions (20 XP each) totaling to 60 XP.
        Triggering the granted and promotion notifications
        """
        # should be no notifications at the start
        self.assertEqual(Notification.objects.all_for_user(self.student).count(), 0)

        # check for false positive
        # 40 XP < Digital Noob (60 XP)
        BadgeAssertion.objects.create_assertion(self.student, self.badge)
        BadgeAssertion.objects.create_assertion(self.student, self.badge)

        # notification: 2 granted
        self.assertEqual(Notification.objects.all_for_user(self.student).count(), 2)

        # should promote student
        # 60 XP (20 + 20 + 20) == Digital Noob (60 XP)
        BadgeAssertion.objects.create_assertion(self.student, self.badge)

        # notifications: 3 granted, 1 promoted
        notifications = Notification.objects.all_for_user(self.student)
        self.assertEqual(notifications.count(), 4)
        self.assertEqual(notifications.filter(verb__contains='granted').count(), 3)
        self.assertEqual(notifications.filter(verb__contains='promoted').count(), 1)
