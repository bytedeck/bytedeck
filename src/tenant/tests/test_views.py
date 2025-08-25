from unittest.mock import patch

from django.conf import settings
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from tenant.views import non_public_only_view, public_only_view, TenantCreate, TenantForm
from tenant.models import Tenant
from tenant.utils import DeckRequestService
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
        self.factory = RequestFactory()

        # Create the public schema
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
            # Use 'testserver' as the domain for environment-agnostic testing
            self.public_tenant.domains.create(domain="testserver", is_primary=True)

        # Create client for the tenant
        self.client = TenantClient(self.public_tenant, host="testserver")

        self.form_data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "captcha": "dummy",
        }

    def test_anonymous_denied_without_verified_deck_request(self):
        """Anonymous users without a verified deck request are denied access."""
        response = self.client.get(reverse("tenant:new"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "tenant/deck_request_denied.html")

    def test_form__errors_for_missing_fields(self):
        """Form errors occur if first_name, last_name, or invalid email are missing."""
        self.client.force_login(self.superuser)

        # Simulate a validated deck request in session
        session = self.client.session
        session["verified_deck_request"] = {"email": "john.doe@example.com"}
        session.save()

        # Missing first_name / last_name
        form_data = {"name": "default", "email": "john.doe@example.com"}
        response = self.client.post(reverse("tenant:new"), data=form_data, follow=True)
        # Check that the error message for required fields is present
        self.assertContains(response, "This field is required", count=2)

        # Invalid email
        form_data.update({"first_name": "John", "last_name": "Doe", "email": "john.doe@example"})
        response = self.client.post(reverse("tenant:new"), data=form_data, follow=True)
        # Check for invalid email error
        self.assertContains(response, "Enter a valid email address")

    @patch("tenant.forms.ReCaptchaField.clean", return_value="PASSED")
    @patch.object(DeckRequestService, "send_verification_email")
    def test_successful_deck_request_sends_email_and_shows_message(self, mock_send_email, mock_captcha):
        """
        Ensure that submitting a valid deck request triggers the verification
        email to be sent and returns a redirect response.
        """
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "captcha": "dummy",
        }
        response = self.client.post(reverse("decks:request_new_deck"), data=form_data)
        mock_send_email.assert_called_once()
        self.assertEqual(response.status_code, 302)

    def test_tenant_form_saves_owner_correctly(self):
        """TenantForm should save tenant and create deck owner from verified data."""
        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        tenant = form.save()

        with tenant_context(tenant):
            site_config = SiteConfig.objects.get()
            owner = site_config.deck_owner

            self.assertEqual(owner.first_name, "John")
            self.assertEqual(owner.last_name, "Doe")
            self.assertEqual(owner.email, "john.doe@example.com")

    def test_form_valid_creates_tenant_and_redirects(self):
        """TenantCreate.form_valid should save tenant, assign deck owner, and redirect."""
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.session = {"verified_deck_request": self.form_data}

        view = TenantCreate()
        view.setup(request)

        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        tenant = form.instance

        with tenant_context(tenant):
            site_config = SiteConfig.objects.get()
            self.assertIsInstance(site_config.deck_owner, User)
            self.assertEqual(site_config.deck_owner.email, "john.doe@example.com")
