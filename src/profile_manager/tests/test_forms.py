from django.contrib.auth import get_user_model
from django.test import RequestFactory

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, generate_form_data
from profile_manager.forms import ProfileForm
from siteconfig.models import SiteConfig

from unittest.mock import patch, MagicMock
import dns.exception
import dns.resolver


User = get_user_model()


class ProfileFormTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student user whose profile is used across the form tests."""
        cls.user = User.objects.create_user('test_student')

    def test_init__with_and_without_request(self):
        """ProfileForm can be instantiated both with and without a request kwarg."""
        # Without request
        ProfileForm(instance=self.user.profile)

        request = RequestFactory().get('/')

        ProfileForm(instance=self.user.profile, request=request)

    def test_save__without_request(self):
        """
        Test to increase coverage for ProfileForm
        """
        form_data = generate_form_data(model_form=ProfileForm)
        form = ProfileForm(instance=self.user.profile, data=form_data)
        form.is_valid()
        form.save()

    def tearDown(self) -> None:
        """Remove the test user after each test."""
        self.user.delete()

    def test_clean_email__valid(self):
        """
        Valid emails should pass validation and resolve (mocked)
        """
        form = ProfileForm(instance=self.user.profile, data={'email': 'example@gmail.com'})
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.return_value = MagicMock()  # Mocking resolve() because we may not have internet access during tests.
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

    def test_clean_email__dns_lookup_error_fails_open(self):
        """A DNS lookup failure that isn't NXDOMAIN (NoNameservers, a timeout, resolver
        misconfiguration, etc.) means we simply couldn't verify the domain — not that it's
        invalid. clean_email should fail open and accept the email rather than let the
        exception propagate and 500 the whole profile form (issue #1976). Without the broad
        dns.exception.DNSException handler these would crash instead of validating.
        """
        for exc in (dns.resolver.NoNameservers, dns.resolver.LifetimeTimeout, dns.exception.Timeout):
            with self.subTest(exception=exc.__name__):
                form = ProfileForm(instance=self.user.profile, data={'email': 'example@gmail.com'})
                with patch('dns.resolver.resolve', side_effect=exc):
                    self.assertTrue(form.is_valid())
                    self.assertEqual(form.cleaned_data['email'], 'example@gmail.com')

    def test_clean_email__deck_owner_cannot_remove(self):
        """The deck owner may not clear their email — ByteDeck needs to contact them (#1502)."""
        # Use a separate user as the deck owner: SiteConfig.deck_owner is a PROTECT FK, so
        # making self.user the owner would break tearDown's self.user.delete().
        owner = User.objects.create_user('deck_owner_user', is_staff=True)
        config = SiteConfig.get()
        config.deck_owner = owner
        config.save()

        form = ProfileForm(instance=owner.profile, data={'email': ''})
        self.assertFalse(form.is_valid())
        self.assertIn(
            "As the deck owner, you can't remove your email address — ByteDeck needs a way to "
            "contact you. You can change it, but it can't be left blank.",
            form.errors['email'],
        )

    def test_clean_email__deck_owner_can_change(self):
        """The deck owner can still change their email to another valid address (#1502)."""
        owner = User.objects.create_user('deck_owner_user', is_staff=True)
        config = SiteConfig.get()
        config.deck_owner = owner
        config.save()

        form = ProfileForm(instance=owner.profile, data={'email': 'owner@gmail.com'})
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.return_value = MagicMock()  # no internet during tests
            form.is_valid()
        self.assertNotIn('email', form.errors)
        self.assertEqual(form.cleaned_data['email'], 'owner@gmail.com')

    def test_clean_email__non_owner_can_remove(self):
        """A regular user (not the deck owner) may still clear their email (#1502)."""
        # self.user is not the deck owner by default.
        self.assertNotEqual(self.user.id, SiteConfig.get().deck_owner_id)

        form = ProfileForm(instance=self.user.profile, data={'email': ''})
        form.is_valid()
        self.assertNotIn('email', form.errors)
        self.assertEqual(form.cleaned_data['email'], '')

    def test_save__with_custom_profile_field(self):
        """ tests if user can create a profile with `custom_profile_field` when SiteConfig.custom_profile_field
        is filled/not filled
        """
        config = SiteConfig.get()

        self.assertEqual(config.custom_profile_field, '')
        self.assertIsNone(self.user.profile.custom_profile_field)

        form = ProfileForm(instance=self.user.profile, data={'custom_profile_field': 'test'})
        form.save()

        # should not affect profile because SiteConfig.custom_profile_field is empty
        # form's custom_profile_field should not exist either
        self.assertIsNone(form.fields.get('custom_profile_field'))
        self.assertIsNone(self.user.profile.custom_profile_field)

        config.custom_profile_field = 'FIELD'
        config.save()

        # need to remake the form since `custom_profile_field` was popped in __init__
        form = ProfileForm(instance=self.user.profile, data={'custom_profile_field': 'test'})
        form.save()

        # should update user.profile and the name of frontend label of `custom_profile_field` should be changed
        self.assertEqual(form.fields['custom_profile_field'].label, 'FIELD')
        self.assertEqual(self.user.profile.custom_profile_field, 'test')
