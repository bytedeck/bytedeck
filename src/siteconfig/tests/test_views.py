from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
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
        del data['custom_stylesheet']
        del data['custom_javascript']

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

    def test_form_helper_required_fields(self):
        """
        Tests whether `form.helper.layout` includes all required fields or not.

        There is an issue with `FormHelper` that breaks form submission, if required fields are not listed explicitly.
        """
        owner_user = self.config.deck_owner

        URL = reverse("config:site_config_update_own")

        # check if owner can change who deck_owner is
        self.client.force_login(owner_user)

        # First case, trying to submit the form with missing fields

        # incomplete payload
        form_data = {
            "site_name": "site_name",
        }
        self.client.post(URL, data=form_data)
        self.assertNotEqual(SiteConfig.get().site_name, "site_name")  # should not be equal and prove the case

        # Second case, trying to find out missing fields

        # get complete list of fields from `generateh_form_data` helper function
        response = self.client.get(URL, data={})
        for f in generate_form_data(model_form=SiteConfigForm).keys():
            # should succeed if `form.helper.layout` is up-to-date
            if f not in str(response.content):
                raise AssertionError(f"'{f}' not found in 'form.helper.layout' list.")

        # Third case, and finally trying to submit with all required (non-blank) fields

        # all required (non-blank) fields
        form_data = {
            "site_name": "site_name",
            "site_name_short": "site_name_short",
            "access_code": "123456",
            "deck_ai": owner_user.pk,
            "custom_name_for_badge": "badge",
            "custom_name_for_announcement": "announcement",
            "custom_name_for_group": "group",
            "custom_name_for_student": "student",
            "custom_name_for_tag": "tag",
            "deck_owner": owner_user.pk,
        }
        self.client.post(URL, data=form_data)
        self.assertEqual(SiteConfig.get().site_name, "site_name")  # should be equal and prove the case

    def test_custom_javascript_mimetypes(self):
        """
        Tests all permitted mimetypes for `custom_javascript` file uploads.
        """
        owner_user = self.config.deck_owner

        URL = reverse("config:site_config_update_own")

        self.client.force_login(owner_user)

        data = model_to_dict(SiteConfig.get())
        del data['banner_image']
        del data['banner_image_dark']
        del data['site_logo']
        del data['default_icon']
        del data['favicon']
        del data['custom_stylesheet']

        # First case, trying uploading file of "application/x-javascript"
        valid_js = b"""alert('Hello, application/x-javascript!');"""
        custom_javascript = InMemoryUploadedFile(
            BytesIO(valid_js),
            field_name="tempfile",
            name="custom.js",
            content_type='application/x-javascript',
            size=len(valid_js),
            charset="utf-8",
        )
        data["custom_javascript"] = custom_javascript

        self.client.post(URL, data=data)
        self.assertEqual(SiteConfig.get().custom_javascript.read(), valid_js)  # form success should have updated model

        # Second case, trying uploading file of "application/javascript"
        valid_js = b"""alert('Hello, application/javascript!');"""
        custom_javascript = InMemoryUploadedFile(
            BytesIO(valid_js),
            field_name="tempfile",
            name="custom.js",
            content_type='application/javascript',
            size=len(valid_js),
            charset="utf-8",
        )
        data["custom_javascript"] = custom_javascript

        self.client.post(URL, data=data)
        self.assertEqual(SiteConfig.get().custom_javascript.read(), valid_js)  # form success should have updated model

        # Third case, trying uploading file of "text/javascript"
        valid_js = b"""alert('Hello, text/javascript!');"""
        custom_javascript = InMemoryUploadedFile(
            BytesIO(valid_js),
            field_name="tempfile",
            name="custom.js",
            content_type='text/javascript',
            size=len(valid_js),
            charset="utf-8",
        )
        data["custom_javascript"] = custom_javascript

        self.client.post(URL, data=data)
        self.assertEqual(SiteConfig.get().custom_javascript.read(), valid_js)  # form success should have updated model
