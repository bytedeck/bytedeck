from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from hackerspace_online.tests.utils import generate_form_data
from profile_manager.forms import ProfileForm
from siteconfig.models import SiteConfig

from unittest.mock import patch, MagicMock
import dns.resolver


User = get_user_model()


class ProfileFormTest(TenantTestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user('test_student', password="test_password")

    def test_init(self):
        # Without request
        ProfileForm(instance=self.user.profile)

        request = RequestFactory().get('/')

        ProfileForm(instance=self.user.profile, request=request)

    def test_profile_save_without_request(self):
        """
        Test to increase coverage for ProfileForm
        """
        form_data = generate_form_data(model_form=ProfileForm)
        form = ProfileForm(instance=self.user.profile, data=form_data)
        form.is_valid()
        form.save()

    def tearDown(self) -> None:
        self.user.delete()

    def test_clean_email__valid(self):
        """
        Valid emails should pass validation and resolve (mocked)
        """
        form = ProfileForm(instance=self.user.profile, data={'email': 'example@gmail.com'})
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.return_value = MagicMock()  # Mocking resolve() because we may not have interent access during tests.
            form.is_valid()
            cleaned_email = form.cleaned_data['email']
            self.assertEqual(cleaned_email, 'example@gmail.com')

    def test_clean_email__invalid_syntax(self):
        """
        Entering a non-email string should raise a ValidationError.  It will actually be caught on the browser side preventing form submission
        but entering it server side shouldn't break the form.
        """
        form = ProfileForm(instance=self.user.profile, data={'email': 'notanemail'})
        self.assertFalse(form.is_valid())
        self.assertIn("Enter a valid email address.", form.errors["email"])

    def test_clean_email__invalid_domain(self):
        """ Mock the NXDOMAIN error from non-existant domains, email field should raise a ValidationError """
        form = ProfileForm(instance=self.user.profile, data={'email': 'example@nonexistentdomain.com'})

        # Mock the NXDOMAIN error from DNS resolution
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NXDOMAIN

            form.is_valid()
            # Assert that the expected validation message is present in the form errors
            self.assertIn(
                "nonexistentdomain.com doesn't appear to exist. Enter a valid email address or leave it blank.",
                form.errors['email']
            )

    def test_clean_email__domain_no_answer(self):
        """ Mock a NoAnswer exception and mack sure it passes email validation.  Some domains don't answer, such as sd72.bc.ca!"""
        form = ProfileForm(instance=self.user.profile, data={'email': 'example@domainwithnoanswer.com'})
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NoAnswer
            form.is_valid()
            cleaned_email = form.cleaned_data['email']
            self.assertEqual(cleaned_email, 'example@domainwithnoanswer.com')

    def test_profile_with_custom_profile_field(self):
        """ tests if user can create a profile with `custom_profile_field` when SiteConfig.custom_profile_field
        is filled/not filled
        """
        config = SiteConfig.get()

        self.assertEqual(config.custom_profile_field, '')
        self.assertEqual(self.user.profile.custom_profile_field, None)

        form = ProfileForm(instance=self.user.profile, data={'custom_profile_field': 'test'})
        form.save()

        # should not affect profile because SiteConfig.custom_profile_field is empty
        # form's custom_profile_field should not exist either
        self.assertEqual(form.fields.get('custom_profile_field'), None)
        self.assertEqual(self.user.profile.custom_profile_field, None)

        config.custom_profile_field = 'FIELD'
        config.save()

        # need to remake the form since `custom_profile_field` was popped in __init__
        form = ProfileForm(instance=self.user.profile, data={'custom_profile_field': 'test'})
        form.save()

        # should update user.profile and the name of frontend label of `custom_profile_field` should be changed
        self.assertEqual(form.fields['custom_profile_field'].label, 'FIELD')
        self.assertEqual(self.user.profile.custom_profile_field, 'test')
