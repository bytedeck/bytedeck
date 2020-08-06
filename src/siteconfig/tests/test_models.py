from django.templatetags.static import static
from django.urls import reverse

from tenant_schemas.test.cases import TenantTestCase
from model_bakery import baker

from siteconfig.models import SiteConfig


class SiteConfigModelTest(TenantTestCase):
    """Tests for the SiteConfig model
    """

    def setUp(self):
        """TenantTestCase generates a tenant for tests.
        Each tenant should have a single SiteConfig object 
        that is created upon first access via the get() method.
        """
        self.config = SiteConfig.get()

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
