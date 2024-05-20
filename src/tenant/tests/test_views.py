from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.account.adapter import get_adapter
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from tenant.views import non_public_only_view, public_only_view, email_confirmed_handler
from tenant.models import Tenant
from siteconfig.models import SiteConfig

User = get_user_model()


# Create a views for testing the mixins/decorators
@public_only_view
def view_accessible_by_public_only(request):
    return HttpResponse(status=200)


@non_public_only_view
def view_accessible_by_non_public_only(request):
    return HttpResponse(status=200)


class ViewsTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # generate an empty request instance so we can call our views directly
        self.request = self.factory.get('/does/not/exist/')

    def test_public_only_view__non_public_tenant(self):
        """Non-public tenant can't access views with the `public_only_view` decorator"""
        # We're in the test tenant by default, so shouldn't be able to access:
        with self.assertRaises(Http404):
            view_accessible_by_public_only(self.request)

    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_public_only_view__public_tenant(self, mock_connection):
        """Public tenant can access views with the `public_only_view` decorator"""
        # we mocked the public tenant, so should be able to
        response = view_accessible_by_public_only(self.request)
        self.assertEqual(response.status_code, 200)

    def test_non_public_only_view__non_public_tenant(self):
        """Non-public tenant can access views with the `non_public_only_view` decorator"""
        # By default we are in the "test" tenant, so should be able to use the view
        response = view_accessible_by_non_public_only(self.request)
        self.assertEqual(response.status_code, 200)

    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_non_public_only_view__public_tenant(self, mock_connection):
        """Public tenant can't access views with the `non_public_only_view` decorator"""
        # We are mocking the public tenant
        with self.assertRaises(Http404):
            view_accessible_by_non_public_only(self.request)


class TenantCreateViewTest(ViewTestUtilsMixin, TenantTestCase):
    """Various tests for `TenantCreate` view class."""

    def setUp(self):
        # create the public schema
        self.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(self.public_tenant):
            # create superuser account
            self.superuser = User.objects.create_superuser(
                username="admin",
                password=settings.TENANT_DEFAULT_ADMIN_PASSWORD,
            )
            # Hack to create the public tenant without triggering the signals,
            # since "setUp" method run before each test, avoiding triggering
            # django signals (post_save and pre_save) can save us a lot of time.
            Tenant.objects.bulk_create([self.public_tenant])
            self.public_tenant.refresh_from_db()
            # create domain object manually, since we avoided triggering the signals
            self.public_tenant.domains.create(domain="localhost", is_primary=True)

        self.client = TenantClient(self.public_tenant)

    def test_default(self):
        """
        Creating new tenant object with valid data, should pass without errors.
        """
        # first case, access /decks/new/ page as anonymous user
        # should returns 302 (login required, note: it's admin/login/ page)
        response = self.client.get(reverse("tenant:new"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual("{}?next={}".format(reverse("admin:login"), reverse("tenant:new")), response.url)

        self.client.force_login(self.superuser)

        # second case, forgot to enter "first" and "last" names
        # should returns 200 (same page, but with errors)
        form_data = {
            "name": "default",
            "email": "john.doe@example.com",
        }
        response = self.client.post(reverse("tenant:new"), data=form_data)
        self.assertEqual(response.status_code, 200)

        # third case, incorrect email address
        # should returns 200 (same page, but with errors)
        form_data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example",  # incorrect email address
        }
        response = self.client.post(reverse("tenant:new"), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")

        # fourth (final) case, and finally trying to submit with all required (non-blank) fields
        # should returs 302 (redirect to newly created tenant)
        form_data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }
        response = self.client.post(reverse("tenant:new"), data=form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://default.localhost:8000")

        # check mailbox after submitting form
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Please Confirm Your Email Address", mail.outbox[0].subject)
        # expecting to see john.doe@example.com as recipient
        self.assertEqual(mail.outbox[0].to, ['john.doe@example.com'])
        # expecting to see correct domain name in confirmation link and make sure link is correct
        email_address = EmailAddress.objects.get(email="john.doe@example.com")
        key = EmailConfirmationHMAC(email_address).key
        confirmation_link = "".join(["http://default.localhost:8000", reverse("account_confirm_email", args=[key])])
        self.assertIn(confirmation_link, mail.outbox[0].body)

        owner = SiteConfig.get().deck_owner or None
        self.assertEqual(owner.get_full_name(), "John Doe")  # should be equal and prove the case
        self.assertEqual(owner.email, "john.doe@example.com")

        # check that the username was set to firstname.lastname (instead of "owner")
        self.assertEqual(owner.username, "john.doe")  # should be equal and prove the case
        # check that the  password was set to firstname-deckname-lastname (instead of "password")
        self.assertEqual(owner.check_password("john-default-doe"), True)

        # manually verify email
        email_address_obj = owner.emailaddress_set.get(email="john.doe@example.com")
        get_adapter(response.wsgi_request).confirm_email(response.wsgi_request, email_address_obj)

        # clear the outbox from outdated messages
        mail.outbox.clear()

        # confirming the email/account and receiving welcome email
        email_confirmed_handler(email_address=email_address_obj)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Instructions to sign in to default", mail.outbox[0].subject)
        # expecting to see the same john.doe@example.com as recipient
        self.assertEqual(mail.outbox[0].to, ['john.doe@example.com'])

        # ... make sure only non-logged users receives "welcome" email
        self.client.force_login(owner)

        # clear the outbox from outdated messages
        mail.outbox.clear()

        # trying to confirm email after being logged into app...
        email_confirmed_handler(email_address=email_address_obj)
        # expect to receive nothing...
        self.assertEqual(len(mail.outbox), 0)
