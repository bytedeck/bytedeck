from unittest.mock import PropertyMock, Mock, patch

from django.conf import settings
from django.core.cache import cache
from django.views import View
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
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
        """Build a public schema, superuser, and TenantClient, and clear the
        per-email throttle cache so each test starts from a clean slate."""
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
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.user = AnonymousUser()
        request.session = {"verified_deck_request": {**self.form_data, "nonce": nonce}}

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
        """TenantCreate.form_valid should save tenant, assign deck owner, redirect,
        and consume the single-use verification nonce."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.user = AnonymousUser()
        request.session = {"verified_deck_request": {**self.form_data, "nonce": nonce}}

        view = TenantCreate()
        view.setup(request)

        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        # tenant creation must happen from the public schema
        with tenant_context(self.public_tenant):
            response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        # the nonce is single-use: it is consumed by a successful creation
        self.assertIsNone(DeckRequestService.peek_request(nonce))

        tenant = form.instance

        with tenant_context(tenant):
            site_config = SiteConfig.objects.get()
            self.assertIsInstance(site_config.deck_owner, User)
            self.assertEqual(site_config.deck_owner.email, "john.doe@example.com")

    @patch("tenant.models.Tenant.full_clean")
    def test_verification_nonce_is_single_use(self, mock_full_clean):
        """A verification nonce provisions at most one deck: a successful creation
        consumes it, and a second attempt with the same nonce is rejected
        (redirected back to the request form) before anything is saved."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")

        def build_request(deck_name):
            # distinct deck names so the second form is valid and reaches
            # form_valid (where the consumed nonce, not a duplicate name, rejects)
            data = {**self.form_data, "name": deck_name}
            request = self.factory.post(reverse("tenant:new"), data=data)
            request.user = AnonymousUser()
            request.session = {"verified_deck_request": {**data, "nonce": nonce}}
            # message storage so form_valid's reject path can add a message
            request._messages = FallbackStorage(request)
            return request, data

        # First creation succeeds and consumes the nonce.
        request1, data1 = build_request("first-deck")
        view1 = TenantCreate()
        view1.setup(request1)
        form1 = TenantForm(data=data1, verified_data=data1)
        self.assertTrue(form1.is_valid(), form1.errors)
        with tenant_context(self.public_tenant):
            response1 = view1.form_valid(form1)
        self.assertEqual(response1.status_code, 302)
        self.assertIsNone(DeckRequestService.peek_request(nonce))

        # Second attempt with the now-consumed nonce is rejected before any save.
        request2, data2 = build_request("second-deck")
        view2 = TenantCreate()
        view2.setup(request2)
        form2 = TenantForm(data=data2, verified_data=data2)
        self.assertTrue(form2.is_valid(), form2.errors)
        response2 = view2.form_valid(form2)
        self.assertEqual(response2.status_code, 302)
        self.assertEqual(response2.url, reverse("decks:request_new_deck"))

    @patch("tenant.models.Tenant.full_clean")
    def test_staff_can_create_deck_without_nonce(self, mock_full_clean):
        """Staff reach TenantCreate without email verification (mixin bypass), so
        form_valid must not require or consume a nonce for them."""
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.user = self.superuser  # staff
        request.session = {"verified_deck_request": self.form_data}  # no nonce

        view = TenantCreate()
        view.setup(request)
        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        with tenant_context(self.public_tenant):
            response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

    def test_verify_deck_request_valid_token_populates_session(self):
        """A valid nonce stores the verified request (including the nonce) in the
        session and redirects to the deck creation form."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        response = self.client.get(reverse("decks:verify_deck_request", args=[nonce]))

        self.assertRedirects(response, reverse("decks:new"), fetch_redirect_response=False)
        verified = self.client.session["verified_deck_request"]
        self.assertEqual(verified["first_name"], "John")
        self.assertEqual(verified["last_name"], "Doe")
        self.assertEqual(verified["email"], "john.doe@example.com")
        self.assertEqual(verified["nonce"], nonce)
        self.assertIn("verified_at", verified)

    def test_verify_deck_request_invalid_token_denied(self):
        """An invalid/expired nonce stores nothing and redirects back to the
        request form."""
        response = self.client.get(reverse("decks:verify_deck_request", args=["not-a-real-nonce"]))

        self.assertRedirects(response, reverse("decks:request_new_deck"), fetch_redirect_response=False)
        self.assertNotIn("verified_deck_request", self.client.session)


class DeckRequestServiceTest(TestCase):
    """Unit tests for the opaque single-use nonce helpers."""

    def setUp(self):
        """Isolate the nonce cache between tests."""
        cache.clear()

    def test_create_and_peek_request_roundtrip(self):
        """A freshly created nonce peeks back to the original requester data."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertEqual(
            DeckRequestService.peek_request(nonce),
            {"first_name": "John", "last_name": "Doe", "email": "john.doe@example.com"},
        )

    def test_peek_unknown_nonce_returns_none(self):
        """An unknown/expired nonce (or None) peeks to None."""
        self.assertIsNone(DeckRequestService.peek_request("not-a-real-nonce"))
        self.assertIsNone(DeckRequestService.peek_request(None))

    def test_peek_does_not_consume(self):
        """Peeking leaves the nonce usable; only creation consumes it."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertIsNotNone(DeckRequestService.peek_request(nonce))
        self.assertIsNotNone(DeckRequestService.peek_request(nonce))

    def test_consume_request_is_single_use(self):
        """The first consume succeeds and removes the nonce; later ones fail."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertTrue(DeckRequestService.consume_request(nonce))
        self.assertFalse(DeckRequestService.consume_request(nonce))
        self.assertIsNone(DeckRequestService.peek_request(nonce))

    def test_consume_none_returns_false(self):
        """Consuming a missing nonce is a no-op that returns False."""
        self.assertFalse(DeckRequestService.consume_request(None))

    def test_verification_link_contains_no_pii(self):
        """The verification URL carries only the opaque nonce, never the
        requester's name or email (unlike a signed token, which would)."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        link = reverse("decks:verify_deck_request", args=[nonce])
        self.assertIn(nonce, link)
        # base64url nonces cannot contain "@" or ".", so these substrings prove
        # the PII is absent regardless of the random nonce value.
        self.assertNotIn("john.doe", link.lower())
        self.assertNotIn("example.com", link.lower())


class DummyView(EmailVerificationRequiredMixin, View):
    """Minimal view used to exercise EmailVerificationRequiredMixin.dispatch."""

    def get(self, request, *args, **kwargs):
        """Return a trivial 200 response when access is granted by the mixin."""
        return HttpResponse("ok")


class EmailVerificationRequiredMixinTest(TestCase):
    def setUp(self):
        """Build a request factory, a stub user with a mocked profile, and the
        DummyView callable used by the access-control assertions."""
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
        """A recent verified_at timestamp grants access (200); a timestamp older
        than TOKEN_MAX_AGE is denied (403)."""
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
