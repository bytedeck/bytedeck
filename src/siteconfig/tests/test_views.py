from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class SiteConfigModelTest(ViewTestUtilsMixin, TenantTestCase):
    """Tests for the SiteConfig model
    """

    def setUp(self):
        """TenantTestCase generates a tenant for tests.
        Each tenant should have a single SiteConfig object 
        that is created upon first access via the get() method.
        """
        self.config = SiteConfig.get()
        self.client = TenantClient(self.tenant)

    def test_SiteConfigUpdateOwn(self):
        """ SiteConfigUpdateOwn is an update view that sets the object to 
        this tenants SiteConfig singleton
        """

        # requires staff member
        self.assertRedirectsAdmin('config:site_config_update_own')

        self.client.force_login(User.objects.create_user(username='staff_test', is_staff=True))
        self.assert200('config:site_config_update_own')

    def test_SiteConfigUpdate(self):
        # requires staff member
        self.assertRedirectsAdmin('config:site_config_update', args=[self.config.get().id])

        self.client.force_login(User.objects.create_user(username='staff_test', is_staff=True))
        self.assert200('config:site_config_update', args=[self.config.get().id])
