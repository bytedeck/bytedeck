from unittest.mock import PropertyMock, Mock, patch

from freezegun import freeze_time

from django.conf import settings
from django.core.cache import cache
from django.views import View
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from tenant.views import non_public_only_view, public_only_view, TenantCreate, TenantForm, EmailVerificationRequiredMixin
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
        # isolate the per-email request throttle between tests
        cache.clear()

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
        mock_captcha.assert_called()
        self.assertEqual(response.status_code, 302)

    @patch("tenant.forms.ReCaptchaField.clean", return_value="PASSED")
    @patch.object(DeckRequestService, "send_verification_email")
    def test_deck_request_throttled_per_email(self, mock_send_email, mock_captcha):
        """The request endpoint sends at most one verification email per address
        within the cooldown, so it can't be used to flood an inbox."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "throttle@example.com",
            "captcha": "dummy",
        }
        self.client.post(reverse("decks:request_new_deck"), data=form_data)
        self.client.post(reverse("decks:request_new_deck"), data=form_data)

        # only the first submission actually sent an email
        mock_send_email.assert_called_once()

    @patch("tenant.models.Tenant.full_clean")
    def test_form_save_persists_tenant_without_touching_owner(self, mock_full_clean):
        """TenantForm.save persists and returns the Tenant only. Owner setup is
        the view's job (done in the tenant's own schema), so the form must not
        touch the owner — it previously mutated SiteConfig.get().deck_owner in
        whatever schema happened to be active."""
        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        # tenant creation must happen from the public schema
        with tenant_context(self.public_tenant):
            tenant = form.save()
            self.assertEqual(tenant.name, "default")
            self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

        with tenant_context(tenant):
            owner = SiteConfig.objects.get().deck_owner
            # the submitted names were NOT applied to the owner by the form
            self.assertNotEqual(owner.first_name, "John")

    @patch("tenant.models.Tenant.full_clean")
    @patch("tenant.views.DeckRequestService.send_welcome_email")
    @patch("tenant.views.generate_default_owner_password", return_value="known-secret-123")
    def test_owner_password_generated_once_and_emailed(self, mock_pw, mock_welcome, mock_full_clean):
        """The owner's password is generated once: the value set on the account
        is the same one handed to the welcome email (a random password would
        otherwise diverge between set and emailed values)."""
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.session = {"verified_deck_request": self.form_data}

        view = TenantCreate()
        view.setup(request)

        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        # tenant creation must happen from the public schema
        with tenant_context(self.public_tenant):
            view.form_valid(form)

        with tenant_context(form.instance):
            owner = SiteConfig.objects.get().deck_owner
            self.assertTrue(owner.check_password("known-secret-123"))

        # the same generated password was handed to the welcome email
        self.assertIn("known-secret-123", mock_welcome.call_args.args)

    @patch("tenant.models.Tenant.full_clean")
    def test_form_valid_creates_tenant_and_redirects(self, mock_full_clean):
        """TenantCreate.form_valid should save tenant, assign deck owner, and redirect."""
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.session = {"verified_deck_request": self.form_data}

        view = TenantCreate()
        view.setup(request)

        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        # tenant creation must happen from the public schema
        with tenant_context(self.public_tenant):
            response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        tenant = form.instance

        with tenant_context(tenant):
            site_config = SiteConfig.objects.get()
            self.assertIsInstance(site_config.deck_owner, User)
            self.assertEqual(site_config.deck_owner.email, "john.doe@example.com")

    def test_verify_deck_request_valid_token_populates_session(self):
        """A valid token stores the verified request in the session and
        redirects to the deck creation form."""
        token = DeckRequestService.generate_token("John", "Doe", "john.doe@example.com")
        response = self.client.get(reverse("decks:verify_deck_request", args=[token]))

        self.assertRedirects(response, reverse("decks:new"), fetch_redirect_response=False)
        verified = self.client.session["verified_deck_request"]
        self.assertEqual(verified["first_name"], "John")
        self.assertEqual(verified["last_name"], "Doe")
        self.assertEqual(verified["email"], "john.doe@example.com")
        self.assertIn("verified_at", verified)

    def test_verify_deck_request_invalid_token_denied(self):
        """An invalid/expired token stores nothing and redirects back to the
        request form."""
        response = self.client.get(reverse("decks:verify_deck_request", args=["not-a-real-token"]))

        self.assertRedirects(response, reverse("decks:request_new_deck"), fetch_redirect_response=False)
        self.assertNotIn("verified_deck_request", self.client.session)


class DeckRequestServiceTest(TestCase):
    """Unit tests for the signed-token helpers."""

    def test_generate_and_decode_token_roundtrip(self):
        token = DeckRequestService.generate_token("John", "Doe", "john.doe@example.com")
        self.assertEqual(
            DeckRequestService.decode_token(token),
            {"first_name": "John", "last_name": "Doe", "email": "john.doe@example.com"},
        )

    def test_decode_token_tampered_returns_none(self):
        token = DeckRequestService.generate_token("John", "Doe", "john.doe@example.com")
        self.assertIsNone(DeckRequestService.decode_token(token + "x"))

    def test_decode_token_expired_returns_none(self):
        with freeze_time("2024-01-01 00:00:00"):
            token = DeckRequestService.generate_token("John", "Doe", "john.doe@example.com")
        # more than TOKEN_MAX_AGE (1 hour) later
        with freeze_time("2024-01-01 02:00:00"):
            self.assertIsNone(DeckRequestService.decode_token(token))


class DummyView(EmailVerificationRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class EmailVerificationRequiredMixinTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User(username="regular")
        self.fake_profile = Mock()
        self.fake_profile.id = 123
        patcher = patch.object(User, "profile", new_callable=PropertyMock, return_value=self.fake_profile)
        self.mock_profile = patcher.start()
        self.addCleanup(patcher.stop)

        self.view = DummyView.as_view()

    @patch("tenant.views.render")  # patch render to avoid template DB queries
    def test_verified_at_allows_or_denies_access(self, mock_render):
        # make render() just return a dummy response
        mock_render.side_effect = lambda request, template_name, context=None, status=None: HttpResponse(status=status or 200)

        fixed_now = timezone.now()

        def make_request(ts):
            request = self.factory.get("/dummy/")
            request.user = self.user
            request.session = {
                "verified_deck_request": {"email": "john.doe@example.com", "verified_at": ts}
            }
            return request

        # Recent timestamp allowed
        recent_ts = fixed_now.timestamp()
        request = make_request(recent_ts)
        response = self.view(request)
        self.assertEqual(response.status_code, 200)

        # Stale timestamp denied
        stale_ts = fixed_now.timestamp() - (DeckRequestService.TOKEN_MAX_AGE + 1)
        request = make_request(stale_ts)
        response = self.view(request)
        self.assertEqual(response.status_code, 403)
