from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from profile_manager.allauth_compat import email_address_exists, send_email_confirmation

User = get_user_model()


class EmailAddressExistsTest(ByteDeckTenantTestCase):
    """Tests for the email_address_exists allauth-compat helper."""

    def test_email_address_exists__found_in_emailaddress_table(self):
        """An email present in allauth's EmailAddress table counts as taken."""
        user = baker.make(User)
        baker.make(EmailAddress, user=user, email='taken@example.com')

        self.assertTrue(email_address_exists('taken@example.com'))

    def test_email_address_exists__found_in_user_email_only(self):
        """An email present only on User.email (no EmailAddress row) still counts as taken."""
        baker.make(User, email='onuser@example.com')

        self.assertTrue(email_address_exists('onuser@example.com'))

    def test_email_address_exists__excludes_the_given_user(self):
        """The email owned only by exclude_user is not counted (the profile being edited)."""
        user = baker.make(User, email='self@example.com')
        baker.make(EmailAddress, user=user, email='self@example.com')

        self.assertFalse(email_address_exists('self@example.com', exclude_user=user))


class SendEmailConfirmationTest(ByteDeckTenantTestCase):
    """Tests for the send_email_confirmation allauth-compat helper."""

    def test_send_email_confirmation__returns_when_no_email(self):
        """With no email on the user (and none passed), the helper returns without sending."""
        user = baker.make(User, email='')

        self.assertIsNone(send_email_confirmation(request=None, user=user))
