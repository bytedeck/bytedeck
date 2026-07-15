from unittest import mock
from django.contrib.auth import get_user_model
from django.utils import timezone

from django_tenants.test.client import TenantClient
from model_bakery import baker
from model_bakery.recipe import Recipe

from badges.models import Badge, BadgeAssertion, BadgeRarity, BadgeSeries, BadgeType
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from notifications.models import Notification
from prerequisites.models import Prereq

User = get_user_model()


class BadgeRarityModelTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        # clear default mark range variables
        BadgeRarity.objects.all().delete()
        cls.common = baker.make(BadgeRarity, percentile=90.0)
        cls.rare = baker.make(BadgeRarity, percentile=80.0)
        cls.ultrarare = baker.make(BadgeRarity, percentile=70.0)

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


class BadgeTypeModelTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.badge_type = baker.make(BadgeType)

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


class BadgeSeriesTestModel(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.badge_series = baker.make(BadgeSeries)

    def test_badge_series_creation(self):
        self.assertIsInstance(self.badge_series, BadgeSeries)
        self.assertEqual(str(self.badge_series), self.badge_series.name)


class BadgeTestModel(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.badge = baker.make(Badge)

    def setUp(self):
        self.client = TenantClient(self.tenant)

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


class BadgeAssertionManagerTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sem = SiteConfig.get().active_semester

        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)
        # cls.assertion = baker.make(BadgeAssertion, semester=cls.sem)
        # cls.badge = Recipe(Badge, xp=20).make()

        # cls.badge_assertion_recipe = Recipe(BadgeAssertion, user=cls.student, badge=cls.badge, semester=cls.sem)

    def setUp(self):
        self.client = TenantClient(self.tenant)

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
        self.assertQuerySetEqual(qs, [badge_assertion, badge_assertion2, badge_assertion3])

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
        self.assertQuerySetEqual(qs, [badge_assertion3, badge_assertion2, badge_assertion])


class BadgeAssertionTestModel(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sem = SiteConfig.get().active_semester

        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)
        cls.assertion = baker.make(BadgeAssertion, semester=cls.sem)
        cls.badge = Recipe(Badge, xp=20).make()

        cls.badge_assertion_recipe = Recipe(BadgeAssertion, user=cls.student, badge=cls.badge, semester=cls.sem)

    def setUp(self):
        self.client = TenantClient(self.tenant)

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
        self.assertQuerySetEqual(list(qs), values, )

    def test_badge_assertions_dict_items_prefetches_duplicates(self):
        """badge_assertions_dict_items pre-populates each distinct badge's
        duplicate assertions, so get_duplicate_assertions() serves them from
        memory with no query per badge (the profile page renders one popover
        per badge)."""
        badge_a = Recipe(Badge, name='Badge A').make()
        badge_b = Recipe(Badge, name='Badge B').make()
        baker.make(BadgeAssertion, user=self.student, badge=badge_a, _quantity=2)
        baker.make(BadgeAssertion, user=self.student, badge=badge_b, _quantity=3)

        items = BadgeAssertion.objects.badge_assertions_dict_items(self.student)
        distinct_assertions = [a for _badge_type, assertions in items for a in assertions]

        duplicate_counts = {}
        with self.assertNumQueries(0):
            for assertion in distinct_assertions:
                duplicate_counts[assertion.badge_id] = len(list(assertion.get_duplicate_assertions()))

        self.assertEqual(duplicate_counts[badge_a.id], 2)
        self.assertEqual(duplicate_counts[badge_b.id], 3)

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
        """ get_by_type_for_user should return one entry per BadgeType, where the entry for the
        granted badge's type contains the user's assertion and all other entries are empty. """
        assertion = self.badge_assertion_recipe.make()
        badge_list_by_type = BadgeAssertion.objects.get_by_type_for_user(self.student)
        self.assertEqual(len(badge_list_by_type), BadgeType.objects.count())
        for entry in badge_list_by_type:
            if entry['badge_type'] == self.badge.badge_type:
                self.assertQuerySetEqual(entry['list'], [assertion])
            else:
                self.assertQuerySetEqual(entry['list'], [])

    def test_badge_assertion_manager_check_for_new_assertions(self):
        """ check_for_new_assertions should grant badges whose prerequisites the user meets,
        including badges unlocked by a badge granted in the same call (recursion). """
        # chain: self.badge -> badge_a -> badge_b
        badge_a = Recipe(Badge, xp=1).make()
        badge_b = Recipe(Badge, xp=1).make()
        Prereq.add_simple_prereq(badge_a, self.badge)
        Prereq.add_simple_prereq(badge_b, badge_a)

        # student hasn't earned self.badge yet, so nothing should be granted
        BadgeAssertion.objects.check_for_new_assertions(self.student)
        self.assertFalse(BadgeAssertion.objects.all_for_user_badge(self.student, badge_a, False).exists())

        # grant the root badge; both dependent badges should now be granted recursively
        self.badge_assertion_recipe.make()
        BadgeAssertion.objects.check_for_new_assertions(self.student)
        self.assertTrue(BadgeAssertion.objects.all_for_user_badge(self.student, badge_a, False).exists())
        self.assertTrue(BadgeAssertion.objects.all_for_user_badge(self.student, badge_b, False).exists())

    def test_fraction_of_active_users_granted_this(self):
        num_students_with_badge = 3

        students_with_badge = baker.make(User, _quantity=num_students_with_badge)
        self.assertEqual(len(students_with_badge), num_students_with_badge)

        total_students = User.objects.filter(is_active=True).count()

        badge = baker.make(Badge)

        for student in students_with_badge:
            baker.make(BadgeAssertion, user=student, badge=badge)

        # fraction_of_active_users_granted_this() caches the active-user and
        # assertion counts for 60s; clear so counts cached by earlier tests in
        # this process can't leak into the assertion below
        from django.core.cache import cache
        cache.clear()

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


class BadgeRarityCacheInvalidationTest(ByteDeckTenantTestCase):
    """get_rarity() reads from the cached rarity list, so every ORM write path
    must invalidate it: save/create and deletes via the post_save/post_delete
    signals, update()/bulk_create()/bulk_update() via the BadgeRarityQuerySet
    overrides (those fire no signals)."""

    def setUp(self):
        """Start each test with a cold rarity cache."""
        from django.core.cache import cache
        cache.delete(BadgeRarity.objects.rarities_cache_key())

    def assert_cache_matches_db(self):
        """Assert the cached rarity list matches the table, comparing (pk, percentile) in percentile order."""
        cached = [(r.pk, r.percentile) for r in BadgeRarity.objects.get_rarities_cached()]
        db = [(r.pk, r.percentile) for r in BadgeRarity.objects.all().order_by('percentile')]
        self.assertEqual(cached, db)

    def warm_cache(self):
        """Populate the rarity cache so the test's write can be shown to invalidate it."""
        BadgeRarity.objects.get_rarities_cached()

    def test_save_invalidates_cache(self):
        """Creating a BadgeRarity (via save) must invalidate the cache (post_save signal)."""
        self.warm_cache()
        rarity = baker.make(BadgeRarity, name='Test Rarity', percentile=0.123)
        self.assertEqual(BadgeRarity.objects.get_rarity(0.1).pk, rarity.pk)
        self.assert_cache_matches_db()

    def test_queryset_delete_invalidates_cache(self):
        """Queryset .delete() must invalidate the cache (receivers disable fast-delete, so post_delete fires)."""
        rarity = baker.make(BadgeRarity, name='Test Rarity', percentile=0.123)
        self.warm_cache()
        BadgeRarity.objects.filter(pk=rarity.pk).delete()
        self.assert_cache_matches_db()

    def test_queryset_update_invalidates_cache(self):
        """Queryset .update() fires no signals; the BadgeRarityQuerySet.update override must invalidate the cache."""
        rarity = baker.make(BadgeRarity, name='Test Rarity', percentile=0.123)
        self.warm_cache()
        BadgeRarity.objects.filter(pk=rarity.pk).update(percentile=0.456)
        self.assert_cache_matches_db()

    def test_bulk_create_invalidates_cache(self):
        """bulk_create() fires no signals; the BadgeRarityQuerySet.bulk_create override must invalidate the cache."""
        self.warm_cache()
        BadgeRarity.objects.bulk_create([BadgeRarity(name='Bulk Rarity', percentile=0.123)])
        self.assert_cache_matches_db()

    def test_bulk_update_invalidates_cache(self):
        """bulk_update() fires no signals; the BadgeRarityQuerySet.bulk_update override must invalidate the cache."""
        rarity = baker.make(BadgeRarity, name='Test Rarity', percentile=0.123)
        self.warm_cache()
        rarity.percentile = 0.456
        BadgeRarity.objects.bulk_update([rarity], ['percentile'])
        self.assert_cache_matches_db()
