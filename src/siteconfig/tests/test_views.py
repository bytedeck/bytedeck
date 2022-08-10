from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.forms.models import model_to_dict
from django.shortcuts import reverse
from django.conf import settings

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

from siteconfig.forms import SiteConfigForm

from hackerspace_online.tests.utils import generate_form_data
from model_bakery import baker

User = get_user_model()


class SiteConfigViewTest(ViewTestUtilsMixin, TenantTestCase):
    """Tests for the SiteConfig View
    """

    def setUp(self):
        """TenantTestCase generates a tenant for tests.
        Each tenant should have a single SiteConfig object
        that is created upon first access via the get() method.
        """
        self.config = SiteConfig.get()
        self.client = TenantClient(self.tenant)

    def test_all_siteconfig_page_status_codes_for_anonymous(self):
        self.assertRedirectsLogin('config:site_config_update', args=[self.config.get().id])
        self.assertRedirectsLogin('config:site_config_update_own')

    def test_all_siteconfig_page_status_codes_for_students(self):
        student = baker.make(User)
        self.client.force_login(student)

        self.assert403('config:site_config_update', args=[self.config.get().id])
        self.assert403('config:site_config_update_own')

    def test_all_siteconfig_page_status_codes_for_staff(self):
        teacher = baker.make(User, is_staff=True)
        self.client.force_login(teacher)

        self.assert200('config:site_config_update', args=[self.config.get().id])
        self.assert200('config:site_config_update_own')

    def testSiteConfigUpdate_uses_newly_saved_cache_data(self):

        self.client.force_login(User.objects.create_user(username='staff_test', is_staff=True))

        old_cache = cache.get(SiteConfig.cache_key())

        data = model_to_dict(old_cache)
        del data['banner_image']
        del data['banner_image_dark']
        del data['site_logo']
        del data['default_icon']
        del data['favicon']

        new_site_name = 'My New Site Name'
        data['site_name'] = new_site_name

        self.client.post(reverse('config:site_config_update_own'), data=data)

        # Cache should be empty at the moment since it was recently deleted via signal
        self.assertIsNone(cache.get(SiteConfig.cache_key()))

        # Call SiteConfig.get() so it sets the cache
        siteconfig = SiteConfig.get()

        # Cache should not be empty
        self.assertIsNotNone(cache.get(SiteConfig.cache_key()))
        # and returns the updated SiteConfig
        self.assertEqual(siteconfig.site_name, new_site_name)

        # After calling SiteConfig.get(), cache should not be equal to the old cache
        # Comparing the `site_name` since Django's Model.__eq__ is comparing `pk`
        self.assertNotEqual(old_cache.site_name, cache.get(SiteConfig.cache_key()).site_name)

    def test_SiteConfigForm_basic_tests(self):
        """ 
            Basic test for SiteConfigForm
        """ 
        owner_user = self.config.deck_owner
        admin_user = User.objects.get(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        staff_user = baker.make(User, is_staff=True,)

        URL = reverse("config:site_config_update_own")

        # NOTE FOR FUTURE TESTS USE SiteConfig.get() INSTEAD OF self.config
        # self.config IS CACHED SO ITS NOT PASSED BY REFERENCE

        # base case (see if something will change)
        self.client.force_login(staff_user)

        test_case = "BASE CASE"
        self.client.post(URL, data=generate_form_data(
            model_form=SiteConfigForm,
            site_name=test_case,
        ))
        self.assertEqual(SiteConfig.get().site_name, test_case)
        self.assertEqual(owner_user.pk, SiteConfig.get().deck_owner.pk)  # owner should be unaffected

        # check if a user who != owner can change SiteConfig deck_owner field
        test_case = "TEST CASE #1"
        self.client.post(URL, data=generate_form_data(
            model_form=SiteConfigForm,
            site_name=test_case, deck_owner=admin_user,
        ))
        self.assertEqual(SiteConfig.get().site_name, test_case)
        self.assertNotEqual(admin_user.pk, SiteConfig.get().deck_owner.pk)  # should not be equal since form prevents non owner from changing owner

        # check if owner can change who deck_owner is 
        self.client.force_login(owner_user)

        test_case = "TEST CASE #2"
        self.client.post(URL, data=generate_form_data(
            model_form=SiteConfigForm,
            site_name=test_case, deck_owner=admin_user,
        ))
        self.assertEqual(SiteConfig.get().site_name, test_case)
        self.assertEqual(admin_user.pk, SiteConfig.get().deck_owner.pk)  # form success should have updated model
