from datetime import timedelta

from django.core.cache import cache
from django.templatetags.static import static
from django.urls import reverse
from django.utils.timezone import localtime

from django_tenants.test.cases import TenantTestCase
from freezegun import freeze_time
from model_bakery import baker

from siteconfig.models import SiteConfig


class SiteConfigModelTest(TenantTestCase):
    """ Tests for the SiteConfig model """

    def setUp(self):
        """TenantTestCase generates a tenant for tests.
        Each tenant should have a single SiteConfig object
        that is created upon first access via the get() method.
        """
        self.config = SiteConfig.get()

    def tearDown(self):
        cache.clear()

    def test_get(self):
        """ Each tenant should have a single SiteConfig object
        that is created upon first access via the get() method
        """
        self.assertIsInstance(self.config, SiteConfig)
        self.assertEqual(SiteConfig.objects.count(), 1)

    def test_semester_created(self):
        """ If one doesn't exists yet, a semester should be created
        to act as the active semester """
        self.assertIsNotNone(self.config.active_semester)

    def test_get_absolute_url(self):
        """ Provides url to the update form """
        self.assertEqual(reverse('config:site_config_update_own'), self.config.get_absolute_url())

    def test_get_site_logo(self):
        """ Returns a default logo """
        self.assertEqual(self.config.get_site_logo_url(), static('img/default_icon.png'))

    def test_get_default_icon_url(self):
        """ By default should return the site logo """
        self.assertEqual(self.config.get_default_icon_url(), static('img/default_icon.png'))

    def test_get_favicon_url(self):
        """ Returns default if no favicon set """
        self.assertEqual(self.config.get_favicon_url(), static('icon/favicon.ico'))

    def test_get_banner_image_url(self):
        self.assertEqual(self.config.get_banner_image_url(), static('img/banner.png'))

    def test_get_banner_image_dark_url(self):
        self.assertEqual(self.config.get_banner_image_dark_url(), static('img/banner.png'))

    def test_set_active_semester(self):
        # make sure default active semester is created first
        default_active_sem = self.config.active_semester
        new_semester = baker.make('courses.Semester')
        # default semester is active
        self.assertNotEqual(new_semester.id, default_active_sem.id)

        # set the new semester with the method
        self.config.set_active_semester(new_semester)
        # make sure it is now the active semester
        self.assertEqual(self.config.active_semester.id, new_semester.id)

    def test_SiteConfig_get_caches(self):
        """ SiteConfig should be in cache """
        cached_config = cache.get(SiteConfig.cache_key())

        self.assertIsNotNone(cached_config)
        self.assertEqual(self.config, cached_config)

    def test_SiteConfig_save_sets_new_cache_properly(self):
        """ SiteConfig.save should invalidate previous cache and set newer cache """
        old_config_cache = cache.get(SiteConfig.cache_key())

        new_site_name = 'My New Site Name'
        self.config.site_name = new_site_name
        self.config.save()

        # Verify SiteConfig.get() is using new cache
        new_config_cache = SiteConfig.get()
        self.assertNotEqual(old_config_cache.site_name, new_config_cache.site_name)

        # Cache should be set after calling SiteConfig.get()
        self.assertEqual(cache.get(SiteConfig.cache_key()).site_name, new_config_cache.site_name)

    def test_SiteConfig_cache_expires(self):
        """ SiteConfig cache should expire after a certain period """

        # Cache should not be empty as of this moment
        self.assertIsNotNone(cache.get(SiteConfig.cache_key()))

        # Cache should now expire
        cache_time_expiration = localtime() + timedelta(days=1)
        with freeze_time(cache_time_expiration, tz_offset=0):
            self.assertIsNone(cache.get(SiteConfig.cache_key()))
