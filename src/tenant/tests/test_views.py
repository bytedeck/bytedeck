from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from tenant.views import non_public_only_view, public_only_view
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
            Tenant.objects.bulk_create([self.public_tenant])
            self.public_tenant.refresh_from_db()
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
        self.assertIn("Please Confirm Your E-mail Address", mail.outbox[0].subject)
        # expecting to see john.doe@example.com as recipient
        self.assertEqual(mail.outbox[0].to, ['john.doe@example.com'])

        owner = SiteConfig.get().deck_owner or None
        self.assertEqual(owner.get_full_name(), "John Doe")  # should be equal and prove the case
        self.assertEqual(owner.email, "john.doe@example.com")
