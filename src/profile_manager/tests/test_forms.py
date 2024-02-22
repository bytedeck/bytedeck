from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from hackerspace_online.tests.utils import generate_form_data
from profile_manager.forms import ProfileForm
from profile_manager.models import Profile

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
        form_data = generate_form_data(
            model_form=ProfileForm,
            grad_year=Profile.get_grad_year_choices()[0][0]
        )
        form = ProfileForm(instance=self.user.profile, data=form_data)
        form.is_valid()
        form.save()

    def tearDown(self) -> None:
        self.user.delete()

    def test_clean_email__valid(self):
        """
        Valid emails should pass validation and resolve (mocked)
        """
        form = ProfileForm(instance=self.user.profile, data={'email': 'example@gmail.com', 'grad_year': Profile.get_grad_year_choices()[0][0]})
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
        form = ProfileForm(instance=self.user.profile, data={'email': 'notanemail', 'grad_year': Profile.get_grad_year_choices()[0][0]})
        self.assertFalse(form.is_valid())
        self.assertIn("Enter a valid email address.", form.errors["email"])

    def test_clean_email__invalid_domain(self):
        """ Mock the NXDOMAIN error from non-existant domains, email field should raise a ValidationError """
        form = ProfileForm(
            instance=self.user.profile,
            data={'email': 'example@nonexistentdomain.com', 'grad_year': Profile.get_grad_year_choices()[0][0]}
        )

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
        form = ProfileForm(
            instance=self.user.profile,
            data={'email': 'example@domainwithnoanswer.com', 'grad_year': Profile.get_grad_year_choices()[0][0]}
        )
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NoAnswer
            form.is_valid()
            cleaned_email = form.cleaned_data['email']
            self.assertEqual(cleaned_email, 'example@domainwithnoanswer.com')
