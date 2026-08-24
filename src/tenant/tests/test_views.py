from unittest.mock import PropertyMock, Mock, patch

from django.conf import settings
from django.core.cache import cache
from django.views import View
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.shortcuts import reverse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.views import (
    non_public_only_view, public_only_view, TenantCreate, TenantForm, EmailVerificationRequiredMixin, _humanize_seconds,
)
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


class ViewsTest(ByteDeckTenantTestCase):
    """Tests the public-only and non-public-only view guards on both the public and tenant schemas."""

    def setUp(self):
        """Build a request factory and an empty request for calling the views directly."""
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


class TenantCreateViewTest(ByteDeckTenantTestCase):
    """Various tests for `TenantCreate` view class."""

    @classmethod
    def setUpTestData(cls):
        """Build a public schema and superuser shared by all tests in the class."""
        # Create the public schema
        cls.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(cls.public_tenant):
            # create superuser account
            cls.superuser = User.objects.create_superuser(
                username="admin",
                password=settings.TENANT_DEFAULT_ADMIN_PASSWORD,
            )
            # Hack to create the public tenant without triggering the signals,
            # avoiding triggering django signals (post_save and pre_save)
            # can save us a lot of time.
            Tenant.objects.bulk_create([cls.public_tenant])
            cls.public_tenant.refresh_from_db()
            # Use 'testserver' as the domain for environment-agnostic testing
            cls.public_tenant.domains.create(domain="testserver", is_primary=True)

        cls.form_data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "captcha": "dummy",
        }

    def setUp(self):
        """Build a TenantClient, and clear the per-email throttle cache so each
        test starts from a clean slate."""
        self.factory = RequestFactory()
        # isolate the per-email request throttle between tests
        cache.clear()

        # Create client for the tenant
        self.client = TenantClient(self.public_tenant, host="testserver")

    def test_get__anonymous_denied_without_verified_deck_request(self):
        """Anonymous users without a verified deck request are denied access."""
        response = self.assert403("tenant:new")
        self.assertTemplateUsed(response, "tenant/deck_request_denied.html")

    def test_get__create_deck_page_extends_public_base_and_keeps_progress_modal(self):
        """The Create New Deck page shares the public onboarding chrome: it renders
        through public/base.html (same navbar/branding as the Request a New Deck
        page) rather than as a standalone document, and still includes the
        deck-generation progress modal that animates on submit. Staff bypass the
        email-verification gate, so the superuser can load the form directly."""
        self.client.force_login(self.superuser)
        response = self.assert200("tenant:new")
        # rendered through the shared public base template (the extension), not standalone
        self.assertTemplateUsed(response, "tenant/tenant_form.html")
        self.assertTemplateUsed(response, "public/base.html")
        # public chrome is present: the navbar brand image only comes from public/base.html
        self.assertContains(response, "pixels-4-icon.png")
        # the progress modal and its form are preserved
        self.assertContains(response, 'id="modalProgress"')
        self.assertContains(response, 'id="form"')

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
    def test_RequestNewDeck_form_valid__sends_email_and_redirects_to_confirmation(self, mock_send_email, mock_captcha):
        """A valid deck request sends the verification email and redirects to the
        dedicated confirmation page (not back to the form with a flash message)."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "captcha": "dummy",
        }
        response = self.client.post(reverse("decks:request_new_deck"), data=form_data)
        mock_send_email.assert_called_once()
        mock_captcha.assert_called()
        self.assertRedirects(
            response,
            reverse("decks:request_new_deck_submitted"),
            fetch_redirect_response=False,
        )

    @patch("tenant.forms.ReCaptchaField.clean", return_value="PASSED")
    @patch.object(DeckRequestService, "send_verification_email")
    def test_deck_request__throttled_per_email(self, mock_send_email, mock_captcha):
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

    @patch("tenant.forms.ReCaptchaField.clean", return_value="PASSED")
    @patch.object(DeckRequestService, "send_verification_email")
    def test_RequestNewDeck_form_valid__redirect_identical_whether_or_not_email_sent(self, mock_send_email, mock_captcha):
        """The response must not reveal whether an email was actually sent: both a
        first (email-sending) request and a throttled second request for the same
        address redirect to the same confirmation page."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "same@example.com",
            "captcha": "dummy",
        }
        first = self.client.post(reverse("decks:request_new_deck"), data=form_data)
        second = self.client.post(reverse("decks:request_new_deck"), data=form_data)

        # the second was throttled (no second email), yet the outcome is identical
        mock_send_email.assert_called_once()
        confirmation_url = reverse("decks:request_new_deck_submitted")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first.url, confirmation_url)
        self.assertEqual(second.url, confirmation_url)

    def test_RequestNewDeckSubmitted_get__renders_workflow_and_timeouts(self):
        """The confirmation page renders through the public base template and lays
        out the 3-step onboarding workflow plus the validity window, single-use
        constraint, spam reminder, and resend cooldown."""
        response = self.assert200("decks:request_new_deck_submitted")
        self.assertTemplateUsed(response, "tenant/request_new_deck_submitted.html")
        self.assertTemplateUsed(response, "public/base.html")

        # the 3-step workflow
        self.assertContains(response, "Verify your email")
        self.assertContains(response, "create your deck")
        self.assertContains(response, "welcome email")
        # spam reminder
        self.assertContains(response, "spam")
        # validity window (TOKEN_MAX_AGE = 3600) + single-use, and resend cooldown
        # (REQUEST_COOLDOWN = 300), surfaced as friendly durations
        self.assertContains(response, "1 hour")
        self.assertContains(response, "one deck")
        self.assertContains(response, "5 minutes")

    def test_RequestNewDeckSubmitted_get__renders_trial_terms(self):
        """The confirmation page's info box states the free-trial terms (length,
        student cap, grace window), sourced from the constants that enforce them
        (maintainer request, 2026-08-08)."""
        from tenant.models import GRACE_PERIOD_DAYS, TRIAL_LENGTH_DAYS, TRIAL_MAX_ACTIVE_USERS

        response = self.client.get(reverse("decks:request_new_deck_submitted"))
        self.assertContains(response, f"free {TRIAL_LENGTH_DAYS}-day trial")
        self.assertContains(response, f"{TRIAL_MAX_ACTIVE_USERS} current student")
        self.assertContains(response, f"{GRACE_PERIOD_DAYS}-day grace period")
        # the info box is an ordinary in-flow alert; the public stylesheet's
        # fixed-toast styling is reserved for the BD-flash flash banner
        self.assertContains(response, "alert alert-warning")
        self.assertNotContains(response, "BD-flash")

    def test_RequestNewDeck_get__outlines_the_flow_steps(self):
        """The request form page outlines the whole flow (verify email, emailed
        credentials, trial terms with a subscribe link, demo-deck preview)
        instead of showing a bare email form (maintainer request, 2026-08-08)."""
        from tenant.models import TRIAL_LENGTH_DAYS, TRIAL_MAX_ACTIVE_USERS

        response = self.assert200("decks:request_new_deck")
        self.assertContains(response, "Verify your email")
        self.assertContains(response, "login credentials")
        self.assertContains(response, f"{TRIAL_LENGTH_DAYS} days")
        self.assertContains(response, f"{TRIAL_MAX_ACTIVE_USERS} student")
        self.assertContains(response, 'href="/pages/subscribe/"')
        self.assertContains(response, 'href="https://learn.bytedeck.com"')
        # the demo course code is unset by default, so no code is printed
        self.assertNotContains(response, "course code")

    @override_settings(DEMO_DECK_COURSE_CODE="join-us-123")
    def test_RequestNewDeck_get__demo_course_code_comes_from_the_environment(self):
        """The demo deck's course code renders only when configured: it lives in
        the deployment's environment rather than the repo, so bots scraping the
        codebase can't harvest it (maintainer request, 2026-08-08)."""
        response = self.client.get(reverse("decks:request_new_deck"))
        self.assertContains(response, "course code")
        self.assertContains(response, "join-us-123")

    def test_RequestNewDeckSubmitted_get_context_data__timeouts_track_configured_values(self):
        """The timeout copy is derived from DeckRequestService's settings, not
        hard-coded: changing the configured values changes the rendered page."""
        with patch.object(DeckRequestService, "TOKEN_MAX_AGE", 7200), \
                patch.object(DeckRequestService, "REQUEST_COOLDOWN", 600):
            response = self.client.get(reverse("decks:request_new_deck_submitted"))
        self.assertContains(response, "2 hours")
        self.assertContains(response, "10 minutes")
        # the old (default) copy must be gone, proving it wasn't hard-coded
        self.assertNotContains(response, "1 hour")
        self.assertNotContains(response, "5 minutes")

    @patch("tenant.models.Tenant.full_clean")
    def test_form_save__persists_tenant_without_touching_owner(self, mock_full_clean):
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
    def test_form_valid__owner_password_generated_once_and_emailed(self, mock_pw, mock_welcome, mock_full_clean):
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
    def test_form_valid__creates_tenant_and_redirects(self, mock_full_clean):
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
    @patch("tenant.views.EmailAddress.objects.get_or_create")
    def test_form_valid__existing_email_address_marked_verified_and_primary(self, mock_get_or_create, mock_full_clean):
        """When the owner already has an EmailAddress, form_valid explicitly marks that
        record verified and primary (the get_or_create created=False branch)."""
        existing_email = Mock()
        mock_get_or_create.return_value = (existing_email, False)

        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        request = self.factory.post(reverse("tenant:new"), data=self.form_data)
        request.user = AnonymousUser()
        request.session = {"verified_deck_request": {**self.form_data, "nonce": nonce}}

        view = TenantCreate()
        view.setup(request)

        form = TenantForm(data=self.form_data, verified_data=self.form_data)
        self.assertTrue(form.is_valid(), form.errors)

        with tenant_context(self.public_tenant):
            view.form_valid(form)

        self.assertTrue(existing_email.verified)
        self.assertTrue(existing_email.primary)
        existing_email.full_clean.assert_called_once()
        existing_email.save.assert_called_once()

    @patch("tenant.models.Tenant.full_clean")
    def test_form_valid__verification_nonce_is_single_use(self, mock_full_clean):
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
    def test_form_valid__staff_can_create_deck_without_nonce(self, mock_full_clean):
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


class HumanizeSecondsTest(TestCase):
    """Tests for the `_humanize_seconds` helper used to surface deck-request
    timeouts on the confirmation page as friendly, non-drifting copy."""

    def test_humanize_seconds__picks_largest_whole_unit_with_correct_plural(self):
        """A whole number of seconds is rendered in the largest exact unit
        (hours, then minutes, then seconds), singular or plural as appropriate."""
        cases = {
            3600: "1 hour",     # TOKEN_MAX_AGE default
            7200: "2 hours",
            300: "5 minutes",   # REQUEST_COOLDOWN default
            60: "1 minute",
            90: "90 seconds",   # not a whole minute -> falls back to seconds
            1: "1 second",
            0: "0 seconds",
        }
        for seconds, expected in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(_humanize_seconds(seconds), expected)

    def test_verify_deck_request__valid_token_populates_session(self):
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

    def test_verify_deck_request__invalid_token_denied(self):
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

    def test_create_and_peek_request__roundtrip(self):
        """A freshly created nonce peeks back to the original requester data."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertEqual(
            DeckRequestService.peek_request(nonce),
            {"first_name": "John", "last_name": "Doe", "email": "john.doe@example.com"},
        )

    def test_peek_request__unknown_nonce_returns_none(self):
        """An unknown/expired nonce (or None) peeks to None."""
        self.assertIsNone(DeckRequestService.peek_request("not-a-real-nonce"))
        self.assertIsNone(DeckRequestService.peek_request(None))

    def test_peek_request__does_not_consume(self):
        """Peeking leaves the nonce usable; only creation consumes it."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertIsNotNone(DeckRequestService.peek_request(nonce))
        self.assertIsNotNone(DeckRequestService.peek_request(nonce))

    def test_consume_request__is_single_use(self):
        """The first consume succeeds and removes the nonce; later ones fail."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        self.assertTrue(DeckRequestService.consume_request(nonce))
        self.assertFalse(DeckRequestService.consume_request(nonce))
        self.assertIsNone(DeckRequestService.peek_request(nonce))

    def test_consume_request__none_returns_false(self):
        """Consuming a missing nonce is a no-op that returns False."""
        self.assertFalse(DeckRequestService.consume_request(None))

    def test_verification_link__contains_no_pii(self):
        """The verification URL carries only the opaque nonce, never the
        requester's name or email (unlike a signed token, which would)."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")
        link = reverse("decks:verify_deck_request", args=[nonce])
        self.assertIn(nonce, link)
        # base64url nonces cannot contain "@" or ".", so these substrings prove
        # the PII is absent regardless of the random nonce value.
        self.assertNotIn("john.doe", link.lower())
        self.assertNotIn("example.com", link.lower())

    def test_build_verification_link__returns_absolute_url_for_nonce(self):
        """build_verification_link turns the nonce's verify path into a fully-qualified URL."""
        request = RequestFactory().get("/")
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")

        link = DeckRequestService.build_verification_link(request, nonce)

        self.assertEqual(link, request.build_absolute_uri(reverse("decks:verify_deck_request", args=[nonce])))
        self.assertIn(nonce, link)
        self.assertTrue(link.startswith("http"))

    @patch("tenant.utils.send_email_message.apply_async")
    def test_send_verification_email__with_request_uses_absolute_link(self, mock_apply_async):
        """With a request, the emailed verification link is absolute, and the message is queued."""
        request = RequestFactory().get("/")
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")

        DeckRequestService.send_verification_email("John", "john.doe@example.com", nonce, request=request)

        mock_apply_async.assert_called_once()
        subject, message, recipients = mock_apply_async.call_args.kwargs["args"]
        self.assertEqual(subject, "Verify your email to confirm your deck request")
        self.assertEqual(recipients, ["john.doe@example.com"])
        self.assertIn(request.build_absolute_uri(reverse("decks:verify_deck_request", args=[nonce])), message)

    @patch("tenant.utils.send_email_message.apply_async")
    def test_send_verification_email__html_body_with_validity_and_logo(self, mock_apply_async):
        """The verification email is a real HTML message: paragraphs, a clickable
        link, the validity window sourced from TOKEN_MAX_AGE rather than
        hard-coded copy, and the platform logo in the standard sigblock.
        send_email_message derives the plain-text part from the HTML, so both
        parts render with formatting instead of one collapsed line."""
        request = RequestFactory().get("/")
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")

        DeckRequestService.send_verification_email("John", "john.doe@example.com", nonce, request=request)

        _subject, message, _recipients = mock_apply_async.call_args.kwargs["args"]
        self.assertIn("<p>Hello John,</p>", message)
        link = request.build_absolute_uri(reverse("decks:verify_deck_request", args=[nonce]))
        self.assertIn(f'<a href="{link}">', message)
        self.assertIn("1 hour", message)  # TOKEN_MAX_AGE = 3600, humanized
        # the platform wordmark at half its 510x128 natural size, by absolute URL
        # so it renders inside email clients (maintainer request, 2026-08-08)
        self.assertIn('alt="[Logo]"', message)
        self.assertIn(f'src="{settings.PUBLIC_EMAIL_LOGO_URL}" width="255" height="64"', message)

    @patch("tenant.utils.send_email_message.apply_async")
    def test_send_verification_email__without_request_uses_relative_link(self, mock_apply_async):
        """Without a request, the emailed verification link is the relative path (no host)."""
        nonce = DeckRequestService.create_request("John", "Doe", "john.doe@example.com")

        DeckRequestService.send_verification_email("John", "john.doe@example.com", nonce, request=None)

        mock_apply_async.assert_called_once()
        _subject, message, _recipients = mock_apply_async.call_args.kwargs["args"]
        self.assertIn(reverse("decks:verify_deck_request", args=[nonce]), message)
        self.assertNotIn("testserver", message)  # relative link, so no absolute host


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
    def test_dispatch__verified_at_allows_or_denies_access(self, mock_render):
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

    @patch("tenant.views.render")  # patch render to avoid template DB queries
    def test_dispatch__verified_request_without_timestamp_is_cleared_and_denied(self, mock_render):
        """A verified_deck_request carrying no verified_at is treated as malformed: it's dropped from the session and access is denied (403)."""
        mock_render.side_effect = lambda request, template_name, context=None, status=None: HttpResponse(status=status or 200)

        request = self.factory.get("/dummy/")
        request.user = self.user
        request.session = {"verified_deck_request": {"email": "john.doe@example.com"}}  # no verified_at

        response = self.view(request)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("verified_deck_request", request.session)


class DeckStatusBannerTest(ByteDeckTenantTestCase):
    """Rendering tests for the deck status banner in base.html (epic #1729 PR 3;
    closes the Trial Mode banner checkbox of #1730)."""

    def setUp(self):
        """Log in per-role users and clear the cached deck row (the cache backend
        outlives each test's transaction)."""
        from django.core.cache import cache
        from model_bakery import baker

        from tenant.utils import deck_cache_key

        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.staff = baker.make(User, is_staff=True)
        self.student = baker.make(User)

    def set_deck(self, **fields):
        """Persist billing fields on this deck via save() so the cache invalidates."""
        for name, value in fields.items():
            setattr(self.tenant, name, value)
        self.tenant.save()

    def get_quests_page(self, user):
        """Return the quest-list page (which extends base.html) as the given user."""
        self.client.force_login(user)
        response = self.assert200('quests:quests')
        return response

    def test_banner__renders_inside_messages_container(self):
        """The banner renders INSIDE #messages-container so it inherits the exact
        same alert styling (margins) as django messages -- outside it, the
        container-scoped rules in custom_common.css don't apply and the banner
        sits flush against the navbar with a mismatched gap below (#2132)."""
        response = self.get_quests_page(self.staff)
        content = response.content.decode()
        # before the fix the banner rendered above (before) the container, so the
        # container's opening tag appearing first is exactly what the fix changes
        self.assertLess(content.index('id="messages-container"'), content.index('id="deck-status-banner"'))

    def test_banner__trial_mode_shown_to_staff_with_subscribe_link(self):
        """Staff on a trial deck see the Trial Mode banner linking to the deck's own
        subscription page (PR 6; previously the public subscribe flatpage)."""
        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Trial Mode')
        self.assertContains(response, 'fa-info-circle')  # banner level icon (review request)
        self.assertContains(response, reverse('decks:subscription'))

    def test_banner__trial_mode_shows_days_remaining_and_live_seat_usage(self):
        """The trial banner's one-line copy shows the short date, the time remaining,
        and the LIVE seats-used count -- a student registered moments ago counts even
        though the nightly-cached field still says 0 (production find: banner claimed
        0 seats used beside a student list showing 1)."""
        from datetime import timedelta

        from django.template.defaultfilters import date as date_filter
        from django.utils.timezone import localdate

        from model_bakery import baker

        from siteconfig.models import SiteConfig

        end = localdate() + timedelta(days=52)
        # cached count deliberately left at 0: the live count must win
        self.set_deck(trial_end_date=end, active_user_count=0, max_active_users=5)
        baker.make('courses.CourseStudent', user=baker.make(User), active=True,
                   semester=SiteConfig.get().active_semester)
        response = self.get_quests_page(self.staff)
        self.assertContains(response, f'until {date_filter(end, "j M Y")}')
        self.assertContains(response, '52 days remain')
        # template whitespace collapses in HTML; normalize before asserting the sentence
        text = ' '.join(response.content.decode().split())
        self.assertIn('You are using 1 out of max 5 current students.', text)
        self.assertContains(response, 'Subscription details')

    def test_banner__trial_mode_unlimited_deck_shows_no_seat_limit(self):
        """A trial deck with the -1 unlimited cap says "unlimited" instead of
        "max -1"."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() + timedelta(days=52), max_active_users=-1)
        response = self.get_quests_page(self.staff)
        text = ' '.join(response.content.decode().split())
        self.assertIn('You are using 0 out of unlimited current students.', text)
        self.assertNotIn('max -1', text)

    def test_banner__not_shown_to_students_on_trial_deck(self):
        """Students never see the trial banner (it's staff-facing nagware)."""
        response = self.get_quests_page(self.student)
        self.assertNotContains(response, 'deck-status-banner')

    def test_banner__suspended_deck_warns_owner_and_visitors(self):
        """On a suspended deck the banner reaches the two audiences who can still
        load pages: the deck owner (the staff variant with the owner-only sign-in
        rule, the 365-day deletion countdown, and the subscribe link) and
        anonymous visitors on the sign-in page (the everyone-else variant).
        Signed-in non-owners are signed out by the suspension middleware before
        any page renders; that path is exercised in test_middleware.py
        (test_bounce__non_owner_is_signed_out_and_redirected_with_message)."""
        from datetime import date

        from siteconfig.models import SiteConfig

        self.set_deck(trial_end_date=date(2020, 1, 1), paid_until=None)

        response = self.get_quests_page(SiteConfig.get().deck_owner)
        self.assertContains(response, 'This deck is suspended')
        text = ' '.join(response.content.decode().split())  # template line-wraps mid-phrase
        self.assertIn('Only the deck owner can sign in', text)  # owner-only sign-in rule
        self.assertIn('suspended for 365 days', text)  # deletion countdown
        self.assertContains(response, 'fa-ban')  # danger-level banner icon
        self.assertContains(response, reverse('decks:subscription'))

        self.client.logout()
        response = self.client.get(reverse('account_login'))
        self.assertContains(response, 'This deck is suspended')
        self.assertContains(response, 'Only the deck owner can sign in')

    def test_banner__over_limit_warns_staff_from_live_count(self):
        """Staff see the over-limit warning from the LIVE current-student count --
        a stale cached count (still 0 here) neither hides a real overage nor keeps
        the warning up after students were archived."""
        from model_bakery import baker

        from siteconfig.models import SiteConfig

        self.set_deck(active_user_count=0, max_active_users=1)
        for _ in range(2):
            baker.make('courses.CourseStudent', user=baker.make(User), active=True,
                       semester=SiteConfig.get().active_semester)

        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Current-student limit exceeded')
        self.assertContains(response, 'this deck has 2')
        self.assertContains(response, 'fa-exclamation-triangle')  # warning-level banner icon

    def test_banner__expiring_soon_warns_staff(self):
        """Staff see the expiring-soon warning inside the two-week window, for both
        trial and subscribed decks."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() + timedelta(days=3))
        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Trial ending soon')

        self.set_deck(trial_end_date=None, paid_until=localdate() + timedelta(days=3))
        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Subscription expiring')

    def test_banner__expired_grace_deck_gets_danger_styling_and_grace_copy(self):
        """A deck past paid_until (in grace) gets the DANGER (red) banner -- not the
        approaching-deadline warning style -- and the copy states when the grace
        period ends and that the deck will then be suspended with only the owner
        able to sign in (suspension redesign, 2026-07-30)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=None, paid_until=localdate() - timedelta(days=10))
        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Subscription expired')
        self.assertContains(response, 'alert-danger')
        self.assertContains(response, 'fa-exclamation-triangle')  # banner level icon (review request)
        text = ' '.join(response.content.decode().split())
        self.assertIn('which ends in 20 days', text)
        self.assertIn('the deck will then be suspended (only the deck owner will be able to sign in)', text)
        # the approaching-deadline variants keep the warning style
        self.set_deck(paid_until=localdate() + timedelta(days=3))
        self.assertContains(self.get_quests_page(self.staff), 'alert-warning')
        # self.tenant is shared across the class in memory and set_deck saves the
        # whole object, so clear the paid date or it leaks into later tests
        self.set_deck(paid_until=None)

    def test_banner__extended_trial_outlasting_an_old_paid_date_reads_as_trial(self):
        """With BOTH dates set and the trial the LATER clock (an admin-extended
        trial on a deck whose paid period lapsed long ago), the expired-into-grace
        banner speaks about the TRIAL: the governing clock picks the wording
        (#1734 B4 review find), not whether a paid date exists."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() - timedelta(days=5), paid_until=localdate() - timedelta(days=100))
        response = self.get_quests_page(self.staff)
        self.assertContains(response, 'Trial ended')
        self.assertNotContains(response, 'Subscription expired')
        # clear the paid date so it doesn't leak into later tests (shared instance)
        self.set_deck(paid_until=None)


class DeckDeletionRequestViewTest(ByteDeckTenantTestCase):
    """The owner's standing deletion request and its withdrawal (#2330): the
    subscription page's request/cancel actions, their owner-only guard, the
    operator notification email, and the page states around them."""

    def setUp(self):
        """Log in the deck owner (the only user the actions accept) on a deck
        with a known live trial."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        from model_bakery import baker

        self.owner = SiteConfig.get().deck_owner
        self.staff = baker.make(User, is_staff=True)
        self.student = baker.make(User)
        self.client.force_login(self.owner)
        self.set_deck(
            trial_end_date=localdate() + timedelta(days=30), paid_until=None,
            deletion_requested_on=None, deletion_requested_by='')

    def set_deck(self, **fields):
        """Persist fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(schema_name=self.tenant.schema_name).update(**fields)
        self.tenant.refresh_from_db()

    def request_deletion(self):
        """POST the deletion request and return the response."""
        return self.client.post(reverse('decks:request_deletion'))

    def test_request_and_cancel__drop_the_cached_deck_row(self):
        """Both actions write with a queryset update (no post_save signal), so they
        must drop the hour-long cached row get_current_deck() serves; a cached
        consumer must never see pre-action state (CodeRabbit find on the #2330
        PR). The page itself reads the middleware-fresh request.tenant."""
        from tenant.utils import get_current_deck, deck_cache_key

        with patch("tenant.tasks.send_email_message.apply_async"):
            get_current_deck()  # populate the cached row (no request standing)
            self.client.post(reverse('decks:request_deletion'))
            cached = get_current_deck()  # a fresh cache fill after the action
            self.assertIsNotNone(cached.deletion_requested_on)

            self.client.post(reverse('decks:cancel_deletion_request'))
            self.assertIsNone(get_current_deck().deletion_requested_on)
        cache.delete(deck_cache_key(self.tenant.schema_name))  # leave no cross-test residue

    @patch("tenant.tasks.send_email_message.apply_async")
    def test_request__records_the_request_and_emails_the_operators(self, mock_apply_async):
        """The owner's POST stamps who asked and when, queues ONE operator email
        to SUPPORT_EMAIL naming the deck and requester, and redirects back with
        the received-and-nothing-deleted confirmation."""
        from django.utils.timezone import localdate

        response = self.client.post(reverse('decks:request_deletion'), follow=True)
        self.assertRedirects(response, reverse('decks:subscription'))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.deletion_requested_on, localdate())
        self.assertEqual(self.tenant.deletion_requested_by, self.owner.get_username())

        mock_apply_async.assert_called_once()
        kwargs = mock_apply_async.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["recipient_list"], [settings.SUPPORT_EMAIL])
        self.assertEqual(kwargs["subject"], f"Deck deletion request: {self.tenant.schema_name}")
        self.assertIn(self.tenant.primary_domain_url, kwargs["message"])
        self.assertIn(self.tenant.schema_name, kwargs["message"])
        self.assertIn(self.owner.get_username(), kwargs["message"])
        self.assertIn("Nothing happens on its own", kwargs["message"])
        # addressed to the operators, so no user-facing footer: ByteDeck should
        # not be inviting itself to "contact us" (review find on the #2330 PR)
        self.assertIn("ByteDeck operations", kwargs["message"])
        self.assertNotIn("contact us", kwargs["message"].lower())

        messages_text = [m.message for m in response.context['messages']]
        self.assertTrue(any("Nothing is deleted yet" in m for m in messages_text))

    @patch("tenant.tasks.send_email_message.apply_async")
    def test_request__second_request_is_a_no_op(self, mock_apply_async):
        """Requesting again while a request stands changes nothing and sends no
        second operator email."""
        from django.utils.timezone import localdate

        self.set_deck(deletion_requested_on=localdate(), deletion_requested_by='someone-earlier')
        self.request_deletion()
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.deletion_requested_by, 'someone-earlier')
        mock_apply_async.assert_not_called()

    @patch("tenant.tasks.send_email_message.apply_async")
    def test_request__owner_only(self, mock_apply_async):
        """Anonymous users are sent to login; students get 403; non-owner staff
        are refused with an error naming the owner; none of them create a request."""
        self.client.logout()
        response = self.request_deletion()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

        self.client.force_login(self.student)
        self.assertEqual(self.request_deletion().status_code, 403)

        self.client.force_login(self.staff)
        response = self.request_deletion()
        self.assertRedirects(response, reverse('decks:subscription'))
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.deletion_requested_on)
        mock_apply_async.assert_not_called()

    def test_request__get_not_allowed(self):
        """The action mutates state, so GET is refused (405) for both routes."""
        self.assertEqual(self.client.get(reverse('decks:request_deletion')).status_code, 405)
        self.assertEqual(self.client.get(reverse('decks:cancel_deletion_request')).status_code, 405)

    def test_cancel__clears_the_request(self):
        """The owner's cancel clears both request fields and confirms; canceling
        with nothing pending is a friendly no-op."""
        from django.utils.timezone import localdate

        self.set_deck(deletion_requested_on=localdate(), deletion_requested_by=self.owner.get_username())
        response = self.client.post(reverse('decks:cancel_deletion_request'))
        self.assertRedirects(response, reverse('decks:subscription'))
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.deletion_requested_on)
        self.assertEqual(self.tenant.deletion_requested_by, '')

        response = self.client.post(reverse('decks:cancel_deletion_request'), follow=True)
        messages_text = [m.message for m in response.context['messages']]
        self.assertTrue(any("no deletion request" in m for m in messages_text))

    def test_cancel__owner_only(self):
        """Non-owner staff cannot withdraw the owner's request."""
        from django.utils.timezone import localdate

        self.set_deck(deletion_requested_on=localdate(), deletion_requested_by=self.owner.get_username())
        self.client.force_login(self.staff)
        self.client.post(reverse('decks:cancel_deletion_request'))
        self.tenant.refresh_from_db()
        self.assertIsNotNone(self.tenant.deletion_requested_on)

    def test_page__shows_the_request_panel_and_pending_state(self):
        """The subscription page offers the request to the owner (button + the
        review-first explanation); once a request stands it shows who asked and
        when, the nothing-deleted reassurance, and the cancel action instead."""
        from django.utils.timezone import localdate

        response = self.client.get(reverse('decks:subscription'))
        self.assertContains(response, 'Request deck deletion')
        self.assertContains(response, 'reviews every request')

        self.set_deck(deletion_requested_on=localdate(), deletion_requested_by=self.owner.get_username())
        response = self.client.get(reverse('decks:subscription'))
        self.assertContains(response, 'Deletion requested')
        self.assertContains(response, self.owner.get_username())
        self.assertContains(response, 'Cancel deletion request')
        self.assertNotContains(response, 'Request deck deletion')

    def test_page__non_owner_staff_see_disabled_buttons(self):
        """Other staff see the section with the action disabled and the owner
        named in its popup, mirroring the manage-subscription button."""
        from django.utils.timezone import localdate

        self.client.force_login(self.staff)
        response = self.client.get(reverse('decks:subscription'))
        self.assertContains(response, 'Request deck deletion')
        self.assertContains(response, f'Only the deck owner, {self.owner.get_username()}, can request')

        # with a request standing, the same staff see the disabled cancel action
        self.set_deck(deletion_requested_on=localdate(), deletion_requested_by=self.owner.get_username())
        response = self.client.get(reverse('decks:subscription'))
        self.assertContains(response, 'Cancel deletion request')
        self.assertContains(response, f'Only the deck owner, {self.owner.get_username()}, can cancel')


class SubscriptionDetailViewTest(ByteDeckTenantTestCase):
    """Access and rendering tests for the staff-facing Subscription details page
    (epic #1729 PR 6; maintainer-requested admin-menu page)."""

    def setUp(self):
        """Log in a staff user, clear the cached deck row, and put the deck in a
        known subscribed state (paid 100 days out, cap 30)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        from model_bakery import baker

        from tenant.utils import deck_cache_key

        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.staff = baker.make(User, is_staff=True)
        self.student = baker.make(User)
        self.client.force_login(self.staff)
        self.set_deck(trial_end_date=None, paid_until=localdate() + timedelta(days=100), max_active_users=30)

    def set_deck(self, **fields):
        """Persist billing fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(schema_name=self.tenant.schema_name).update(**fields)
        self.tenant.refresh_from_db()

    def get_page(self):
        """GET the subscription page, asserting 200."""
        response = self.assert200('decks:subscription')
        return response

    def test_page__staff_only(self):
        """Anonymous users are redirected to login; students get 403; staff get 200."""
        self.client.logout()
        self.assertRedirectsLogin('decks:subscription')

        self.client.force_login(self.student)
        self.assert403('decks:subscription')

        self.client.force_login(self.staff)
        self.get_page()

    def test_page__auto_renewing_deck_reads_as_renewing_not_expiring(self):
        """An auto-renewing subscription says what actually happens on its date:
        it renews and the card is charged, with the Dates row labelled "Renews
        on" rather than "Paid until" (#2586). The same deck set to cancel goes
        back to expiry wording."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(paid_until=localdate() + timedelta(days=10), stripe_auto_renews=True)
        response = self.get_page()
        self.assertContains(response, 'Renews automatically on')
        self.assertContains(response, 'Renews on')
        self.assertContains(response, 'renews in 10 days')
        self.assertNotContains(response, 'Paid until')

        self.set_deck(stripe_auto_renews=False)  # cancelled at period end
        response = self.get_page()
        self.assertContains(response, 'Paid until')
        self.assertNotContains(response, 'Renews automatically on')

    def test_page__shows_dates_seats_and_status(self):
        """A subscribed deck shows its status, the governing date, days remaining,
        and the three seat rows (maximum / current / remaining)."""
        response = self.get_page()
        self.assertContains(response, 'Subscribed')
        self.assertContains(response, '100 days remaining')
        self.assertContains(response, 'Paid until')
        self.assertContains(response, 'Current students')
        self.assertContains(response, 'Maximum allowed')
        self.assertContains(response, 'Remaining students')
        self.assertContains(response, '30')

    def test_page__dates_show_relative_time_in_every_state(self):
        """Every Dates row carries a relative phrase: time remaining while the date
        is ahead, or how long ago it passed -- for Paid until, the grace period's
        end, and Trial ends alike (maintainer request from staging live testing)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        # subscribed: paid_until ahead, grace end further ahead
        text = ' '.join(self.get_page().content.decode().split())
        self.assertIn('(100 days remaining)', text)
        self.assertIn('extends 30 days after your subscription ends (ends in 130 days)', text)

        # in grace: paid_until behind, grace end still ahead
        self.set_deck(paid_until=localdate() - timedelta(days=10))
        text = ' '.join(self.get_page().content.decode().split())
        self.assertIn('(expired 10 days ago)', text)
        self.assertIn('(ends in 20 days)', text)

        # suspended: both behind (the maintainer's "ended 24 days ago" example)
        self.set_deck(paid_until=localdate() - timedelta(days=54))
        text = ' '.join(self.get_page().content.decode().split())
        self.assertIn('(expired 54 days ago)', text)
        self.assertIn('(ended 24 days ago)', text)

        # trial deck: the Trial ends row gets the same treatment, both directions
        self.set_deck(paid_until=None, trial_end_date=localdate() + timedelta(days=10))
        self.assertIn('(10 days remaining)', ' '.join(self.get_page().content.decode().split()))
        self.set_deck(trial_end_date=localdate() - timedelta(days=3))
        self.assertIn('(expired 3 days ago)', ' '.join(self.get_page().content.decode().split()))

        # boundary days read "today", singular day is "1 day"
        self.set_deck(trial_end_date=localdate())
        self.assertIn('(expires today)', ' '.join(self.get_page().content.decode().split()))
        self.set_deck(trial_end_date=localdate() + timedelta(days=1))
        self.assertIn('(1 day remaining)', ' '.join(self.get_page().content.decode().split()))
        self.set_deck(trial_end_date=None, paid_until=localdate() - timedelta(days=30))  # final grace day
        self.assertIn('(ends today)', ' '.join(self.get_page().content.decode().split()))

    def test_page__dates_show_only_the_governing_deadline(self):
        """The Dates table shows ONE deadline row -- the governing (LATEST) clock's
        (#1734 B4): Paid until when the paid clock governs, Trial ends when the
        trial clock governs (even with both dates set), and a never-expires row
        on a managed-manually deck."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        # subscribed decks keep their old trial date; the paid clock governs
        self.set_deck(trial_end_date=localdate() - timedelta(days=300))
        response = self.get_page()
        self.assertContains(response, 'Paid until')
        self.assertNotContains(response, 'Trial ends')

        self.set_deck(trial_end_date=localdate() + timedelta(days=10), paid_until=None)
        response = self.get_page()
        self.assertContains(response, 'Trial ends')
        self.assertNotContains(response, 'Paid until')

        self.set_deck(trial_end_date=None, paid_until=None)
        response = self.get_page()
        self.assertContains(response, 'Never')
        self.assertNotContains(response, 'Trial ends')
        self.assertNotContains(response, 'Paid until')

    def test_page__extended_trial_outlasting_an_old_paid_date_reads_as_trial(self):
        """With BOTH dates set and the trial the LATER clock (an admin-extended
        trial on a deck whose paid period lapsed earlier), the grace status and
        the Dates table follow the governing trial clock: trial wording,
        subscribe (not renew), the Trial ends row, and no Paid until row
        (#1734 B4 review find)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() - timedelta(days=5), paid_until=localdate() - timedelta(days=100))
        response = self.get_page()
        text = ' '.join(response.content.decode().split())
        self.assertIn('free trial ended on', text)
        self.assertIn('subscribe to keep full access', text)
        self.assertIn('extends 30 days after your trial ends (ends in 25 days)', text)
        self.assertContains(response, 'Trial ends')
        self.assertNotContains(response, 'Paid until')

    def test_page__remaining_seats_counts_down_and_clamps_at_zero(self):
        """Remaining students = cap minus the LIVE current-student count, clamped
        at 0 when over the limit; None (rendered "Unlimited") on unlimited decks."""
        from model_bakery import baker

        from siteconfig.models import SiteConfig

        self.assertEqual(self.get_page().context['remaining_seats'], 30)

        for _ in range(2):  # two current students on a cap of 1: clamped, not -1
            baker.make('courses.CourseStudent', user=baker.make(User), active=True,
                       semester=SiteConfig.get().active_semester)
        self.set_deck(max_active_users=1)
        response = self.get_page()
        self.assertEqual(response.context['remaining_seats'], 0)

        self.set_deck(max_active_users=-1)
        self.assertIsNone(self.get_page().context['remaining_seats'])

    def test_page__grace_period_states_suspension_ahead(self):
        """A deck in its paid grace window gets its own DANGER "Grace period" label --
        never the green "Subscribed" badge (maintainer review find) -- and explains
        what follows: suspension, with only the deck owner able to sign in and the
        deletion countdown starting (suspension redesign, 2026-07-30)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(paid_until=localdate() - timedelta(days=5))
        response = self.get_page()
        self.assertContains(response, 'Grace period</span>')
        self.assertContains(response, 'label-danger')
        self.assertNotContains(response, 'Subscribed')
        text = ' '.join(response.content.decode().split())
        self.assertIn('otherwise the deck will be suspended (only the deck owner will be able to sign in, '
                      'and the 365-day countdown to deck deletion begins)', text)

    def test_page__lapsed_trial_gets_the_same_grace_status(self):
        """A lapsed trial lands in the SAME grace state (#1734 B4): the danger
        "Grace period" label, trial-specific wording ("free trial ended",
        subscribe rather than renew), and the trial Dates rows with the grace
        row's countdown."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() - timedelta(days=5), paid_until=None)
        response = self.get_page()
        self.assertContains(response, 'Grace period</span>')
        self.assertContains(response, 'label-danger')
        text = ' '.join(response.content.decode().split())
        self.assertIn('free trial ended on', text)
        self.assertIn('subscribe to keep full access', text)
        self.assertIn('extends 30 days after your trial ends (ends in 25 days)', text)

    def test_page__suspended_deck_states_owner_only_and_deletion_countdown(self):
        """A suspended deck's status copy states the suspension rules -- only
        the deck owner can sign in, and the 365-day deletion countdown -- while
        the seats table still shows the ADMIN-SET cap, whatever it is (the
        field stays authoritative; production find, 2026-07-24). Viewed as the
        deck owner: the suspension middleware signs everyone else out (#1734)."""
        from datetime import date

        from siteconfig.models import SiteConfig

        self.set_deck(trial_end_date=date(2020, 1, 1), paid_until=None, max_active_users=1)
        self.client.force_login(SiteConfig.get().deck_owner)
        response = self.get_page()
        self.assertContains(response, 'only the deck owner can sign in')
        self.assertContains(response, 'suspended for 365 days')
        # page status copy specifically (the banner says similar things): data intact + how to restore
        self.assertContains(response, 'Nothing has been deleted yet')
        text = ' '.join(response.content.decode().split())
        self.assertIn('<th>Maximum allowed</th> <td>1</td>', text)

    def test_page__lifecycle_overview_lists_every_stage(self):
        """The "How subscriptions work" section walks the owner through the whole
        lifecycle -- valid subscription, grace period, suspension (owner-only
        sign-in + deletion countdown), deletion -- and pitches the Maintenance
        subscription as the keep-it-safe option (maintainer request, 2026-07-30)."""
        response = self.get_page()
        self.assertContains(response, 'How subscriptions work')
        self.assertContains(response, 'Valid subscription')
        self.assertContains(response, 'Grace period')
        self.assertContains(response, 'Suspension')
        self.assertContains(response, 'Deletion')
        text = ' '.join(response.content.decode().split())
        self.assertIn('Only the deck owner can sign in, and the 365-day countdown to deck deletion begins', text)
        self.assertIn('max 5 current students', text)  # the Maintenance pitch states the trial cap

    def test_page__maintenance_subscription_gets_its_own_status(self):
        """A paid deck whose cap sits at the trial limit is on MAINTENANCE: its own
        status label and copy (kept alive, capped, upgradable) instead of the
        plain green Subscribed badge -- while a paid deck with a higher cap keeps
        the Subscribed status."""
        self.set_deck(max_active_users=5)  # paid 100 days out from setUp
        response = self.get_page()
        self.assertContains(response, 'Maintenance</span>')  # the status label itself
        self.assertContains(response, 'maintenance subscription')
        self.assertContains(response, 'capped at the trial limit')
        self.assertContains(response, 'max 5 current students')
        self.assertNotContains(response, '>Subscribed</span>')

        self.set_deck(max_active_users=30)
        response = self.get_page()
        self.assertContains(response, 'Subscribed')
        # the lifecycle overview always PITCHES Maintenance, so pin the status label only
        self.assertNotContains(response, 'Maintenance</span>')

    def test_page__trial_suspended_and_manual_states(self):
        """The status section adapts to trial, suspended, and never-expires decks."""
        from datetime import date, timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() + timedelta(days=10), paid_until=None)
        self.assertContains(self.get_page(), 'Free trial')

        self.set_deck(trial_end_date=date(2020, 1, 1), paid_until=None)
        self.assertContains(self.get_page(), 'Suspended')

        self.set_deck(trial_end_date=None, paid_until=None)
        self.assertContains(self.get_page(), 'Managed manually')

    def test_page__unlimited_cap_shown_as_unlimited(self):
        """The -1 unlimited sentinel renders as "Unlimited" rather than -1."""
        self.set_deck(max_active_users=-1)
        self.assertContains(self.get_page(), 'Unlimited')

    def test_page__mid_trial_checkout_note_promises_no_lost_trial_time(self):
        """While the deck is on trial (with enough trial left for checkout to
        preserve it), the subscribe button's help text says the card isn't
        charged until the trial ends; a paid deck gets the plain portal/checkout
        copy with no trial note (maintainer decision, 2026-08-06)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        with override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123'):
            self.set_deck(trial_end_date=localdate() + timedelta(days=30), paid_until=None)
            text = ' '.join(self.get_page().content.decode().split())
            self.assertIn("won't cut your free trial short", text)
            self.assertIn('renews automatically', text)

            # subscribed deck: no trial note
            self.set_deck(trial_end_date=None, paid_until=localdate() + timedelta(days=100))
            text = ' '.join(self.get_page().content.decode().split())
            self.assertNotIn("won't cut your free trial short", text)

    def test_page__not_configured_falls_back_to_public_subscribe_page(self):
        """Without Stripe keys the page says billing isn't configured and links the
        public subscribe page instead of rendering the checkout form."""
        from tenant.utils import get_public_subscribe_url

        response = self.get_page()
        self.assertContains(response, "billing isn't configured")
        self.assertContains(response, get_public_subscribe_url())

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_page__configured_shows_checkout_portal_or_manual_note(self):
        """With Stripe configured: an unlinked trial deck gets "Subscribe now", a
        linked deck gets "Manage subscription" (billing portal), and an unlinked
        deck still inside its paid period gets the managed-manually note instead
        of a button (checkout would double-bill it)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=localdate() + timedelta(days=30), paid_until=None)
        self.assertContains(self.get_page(), 'Subscribe now')

        self.set_deck(stripe_customer_id='cus_123', paid_until=localdate() + timedelta(days=100))
        self.assertContains(self.get_page(), 'Manage subscription')

        self.set_deck(stripe_customer_id='')  # actively paid, unlinked: manual
        response = self.get_page()
        self.assertContains(response, 'managed manually')
        self.assertNotContains(response, 'Subscribe now')

    def test_page__status_names_the_plan_after_the_subscribed_badge(self):
        """A linked, subscribed deck's status line names the Stripe plan and its
        renewal terms after the badge -- "Subscribed to <product>, renewed
        annually at $75.00 per year. Paid through ..." (maintainer request,
        2026-08-09) -- and degrades to the plain paid-through line when Stripe
        can't say."""
        self.set_deck(stripe_customer_id='cus_9', stripe_subscription_id='sub_9')
        summary = {'name': 'Bytedeck Subscription - 40 Students', 'renewal_phrase': 'renewed annually at $75.00 per year'}
        with patch('tenant.billing.subscription_plan_summary', return_value=summary):
            text = ' '.join(self.get_page().content.decode().split())
        self.assertIn(
            'Subscribed</span> to <strong>Bytedeck Subscription - 40 Students</strong>, '
            'renewed annually at $75.00 per year. Paid through',
            text,
        )

        with patch('tenant.billing.subscription_plan_summary', return_value=None):
            text = ' '.join(self.get_page().content.decode().split())
        self.assertIn('Subscribed</span> Paid through', text)

    def test_page__maintenance_status_names_the_plan_when_known(self):
        """A maintenance deck's status parenthesizes its plan when Stripe data is
        available: "on a maintenance subscription (<product>, renewed annually
        at $10.00 per year) through ..."."""
        self.set_deck(max_active_users=5, stripe_customer_id='cus_9', stripe_subscription_id='sub_9')
        summary = {'name': 'Bytedeck Maintenance', 'renewal_phrase': 'renewed annually at $10.00 per year'}
        with patch('tenant.billing.subscription_plan_summary', return_value=summary):
            text = ' '.join(self.get_page().content.decode().split())
        self.assertIn(
            'maintenance subscription (<strong>Bytedeck Maintenance</strong>, '
            'renewed annually at $10.00 per year) through',
            text,
        )

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_page__manage_button_shows_at_top_and_bottom_owner_only(self):
        """The manage action appears TWICE -- under Status and in Upgrade-or-renew
        (maintainer request, 2026-08-09). Staff who are not the deck owner get
        both copies disabled with a popup naming who can act; the owner gets the
        live forms with the portal/checkout help text as the title popup."""
        from siteconfig.models import SiteConfig

        owner = SiteConfig.get().deck_owner
        self.set_deck(stripe_customer_id='cus_9')

        # Match the manage-subscription form by its action, so the shared navbar's own
        # sign-out POST form (present on every authenticated page) is never miscounted.
        manage_form = f'<form method="post" action="{reverse("decks:subscription")}">'

        # setUp's staff user is NOT the owner: disabled buttons, owner named in the popup
        response = self.get_page()
        self.assertContains(response, 'Manage subscription', count=2)
        self.assertContains(
            response, f'Only the deck owner, {owner.get_username()}, can manage the subscription.', count=2
        )
        self.assertNotContains(response, manage_form)

        # the owner: two live forms, the help text riding on the buttons' title popups
        self.client.force_login(owner)
        response = self.get_page()
        self.assertContains(response, 'Manage subscription', count=2)
        self.assertContains(response, manage_form, count=2)
        self.assertNotContains(response, 'disabled')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_page__lapsed_linked_deck_button_says_renew(self):
        """A linked deck past its governing deadline (grace or suspended) labels
        the manage action "Renew subscription" with renewal help text: the POST
        routes such a deck to renewal, so the button says so up front
        (production find, 2026-08-09: an expired deck's button read "Manage
        subscription" and led to a portal with nothing actionable on it)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        from siteconfig.models import SiteConfig

        # grace (paid period just lapsed): staff still have access and see renew wording
        self.set_deck(stripe_customer_id='cus_9', trial_end_date=None, paid_until=localdate() - timedelta(days=5))
        response = self.get_page()
        self.assertContains(response, 'Renew subscription', count=2)
        self.assertNotContains(response, 'Manage subscription')

        # suspended (grace fully lapsed): only the owner can still sign in; renew wording holds
        self.client.force_login(SiteConfig.get().deck_owner)
        self.set_deck(paid_until=localdate() - timedelta(days=45))
        response = self.get_page()
        self.assertContains(response, 'Renew subscription', count=2)
        self.assertNotContains(response, 'Manage subscription')

    def test_page__contact_copy_links_the_support_address(self):
        """Copy that says to contact ByteDeck links the support address as a
        mailto (maintainer request, 2026-08-09): the managed-manually status, the
        manual-billing note, and the activating page's check-later copy."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=None, paid_until=None)  # the managed-manually status
        self.assertContains(self.get_page(), 'mailto:contact@bytedeck.com')

        # actively paid + unlinked with Stripe configured: the manual-billing note
        with override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123'):
            self.set_deck(paid_until=localdate() + timedelta(days=100))
            self.assertContains(self.get_page(), 'mailto:contact@bytedeck.com')

        # the activating page's "contact ByteDeck if it still hasn't appeared"
        response = self.client.get(reverse('decks:subscription_activating'))
        self.assertContains(response, 'mailto:contact@bytedeck.com')

    def test_menu__admin_dropdown_links_subscription_page_for_staff(self):
        """The navbar admin menu contains the Subscription entry for staff."""
        response = self.client.get(reverse('quests:quests'))
        self.assertContains(response, reverse('decks:subscription'))
        self.assertContains(response, 'Subscription')


class SubscriptionCheckoutTest(ByteDeckTenantTestCase):
    """Stripe checkout/portal flow tests for the subscription page (epic #1729 PR 6).

    Stripe is never called for real: the SDK entry points used by tenant.billing
    are mocked at that seam.
    """

    def setUp(self):
        """Log in the DECK OWNER (the only user who may start checkout or open the
        portal) on an unlinked deck with billing configured via override in each
        test (the deck's owner email resolution is exercised as-is). A non-owner
        staff member is kept around for the rejection test. The cosmetic
        customer-description stamp is stubbed so link-path tests never attempt a
        real Stripe call."""
        from model_bakery import baker

        from siteconfig.models import SiteConfig

        from tenant.utils import deck_cache_key

        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.staff = baker.make(User, is_staff=True)
        self.owner = SiteConfig.get().deck_owner
        self.client.force_login(self.owner)
        patcher = patch('tenant.billing.stripe.Customer.modify')
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_deck(self, **fields):
        """Persist billing fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(schema_name=self.tenant.schema_name).update(**fields)
        self.tenant.refresh_from_db()

    def test_post__not_configured_shows_error(self):
        """POST without Stripe keys redirects back with an error message and calls
        nothing."""
        response = self.client.post(reverse('decks:subscription'), follow=True)
        self.assertContains(response, "billing isn't configured")

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__unlinked_deck_redirects_to_checkout(self):
        """POST on an unlinked deck creates a subscription Checkout Session carrying
        the deck's identity and redirects to Stripe's URL."""
        with patch('tenant.billing.stripe.checkout.Session.create',
                   return_value=Mock(url='https://checkout.stripe.test/cs_123')) as mock_create:
            response = self.client.post(reverse('decks:subscription'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.test/cs_123')
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs['mode'], 'subscription')
        self.assertEqual(kwargs['client_reference_id'], self.tenant.schema_name)
        self.assertEqual(kwargs['metadata'], {'schema_name': self.tenant.schema_name})
        self.assertEqual(kwargs['line_items'], [{'price': 'price_123', 'quantity': 1}])
        self.assertIn('session_id={CHECKOUT_SESSION_ID}', kwargs['success_url'])
        self.assertIn(reverse('decks:subscription_activating'), kwargs['success_url'])
        self.assertIn(reverse('decks:subscription'), kwargs['cancel_url'])
        self.assertIn(self.tenant.schema_name, kwargs['idempotency_key'])

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__linked_deck_with_live_subscription_redirects_to_billing_portal(self):
        """POST on a deck whose linked Stripe subscription is LIVE opens the
        billing portal for that customer: the portal can act on a live
        subscription (renew, fix the card, switch plans, cancel)."""
        self.set_deck(stripe_customer_id='cus_123', stripe_subscription_id='sub_live')
        with patch('tenant.billing.stripe.Subscription.retrieve', return_value=Mock(status='active')), \
                patch('tenant.billing.stripe.billing_portal.Session.create',
                      return_value=Mock(url='https://portal.stripe.test/ps_123')) as mock_create:
            response = self.client.post(reverse('decks:subscription'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://portal.stripe.test/ps_123')
        self.assertEqual(mock_create.call_args.kwargs['customer'], 'cus_123')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__expired_deck_with_canceled_subscription_renews_via_checkout(self):
        """POST on an expired deck whose old subscription is fully CANCELED gets
        a fresh Checkout bound to its existing customer, NOT a portal session:
        a canceled subscription cannot be restarted from the portal, which
        showed only payment methods and invoices, a dead end exactly when the
        deck was trying to come back (production find, 2026-08-09; this deck
        shape reproduced it: suspended, ids present, subscription canceled)."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(stripe_customer_id='cus_123', stripe_subscription_id='sub_dead',
                      trial_end_date=None, paid_until=localdate() - timedelta(days=45))
        with patch('tenant.billing.stripe.Subscription.retrieve', return_value=Mock(status='canceled')), \
                patch('tenant.billing.stripe.billing_portal.Session.create') as mock_portal, \
                patch('tenant.billing.stripe.checkout.Session.create',
                      return_value=Mock(url='https://checkout.stripe.test/cs_renew')) as mock_checkout:
            response = self.client.post(reverse('decks:subscription'))
        mock_portal.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.test/cs_renew')
        # the checkout is bound to the existing customer: saved cards and
        # invoice history carry over instead of minting a duplicate customer
        self.assertEqual(mock_checkout.call_args.kwargs['customer'], 'cus_123')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__customer_without_subscription_goes_to_checkout(self):
        """POST on a deck with a customer id but NO subscription id (an
        abandoned checkout, or a partial legacy link) starts a Checkout as that
        customer without asking Stripe anything: there is no subscription the
        portal could manage."""
        self.set_deck(stripe_customer_id='cus_123')
        with patch('tenant.billing.stripe.Subscription.retrieve') as mock_retrieve, \
                patch('tenant.billing.stripe.billing_portal.Session.create') as mock_portal, \
                patch('tenant.billing.stripe.checkout.Session.create',
                      return_value=Mock(url='https://checkout.stripe.test/cs_c')) as mock_checkout:
            response = self.client.post(reverse('decks:subscription'))
        mock_retrieve.assert_not_called()
        mock_portal.assert_not_called()
        self.assertEqual(response.url, 'https://checkout.stripe.test/cs_c')
        self.assertEqual(mock_checkout.call_args.kwargs['customer'], 'cus_123')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__manually_subscribed_deck_refused_to_prevent_double_billing(self):
        """An unlinked deck still inside its PAID period has a manually managed
        subscription: checkout is refused (it would create a second, parallel
        subscription), while a lapsed deck in its grace window may renew."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=None, paid_until=localdate() + timedelta(days=100))
        with patch('tenant.billing.stripe.checkout.Session.create') as mock_create:
            response = self.client.post(reverse('decks:subscription'), follow=True)
        mock_create.assert_not_called()
        self.assertContains(response, 'double-bill')
        # the error message renders its contact address as a clickable mailto link
        self.assertContains(response, 'mailto:contact@bytedeck.com')
        # the page itself shows the manual-subscription note instead of the button
        self.assertContains(self.client.get(reverse('decks:subscription')), 'managed manually')

        # in grace (paid period over): renewal via checkout is allowed
        self.set_deck(paid_until=localdate() - timedelta(days=5))
        with patch('tenant.billing.stripe.checkout.Session.create',
                   return_value=Mock(url='https://checkout.stripe.test/cs_g')) as mock_create:
            response = self.client.post(reverse('decks:subscription'))
        self.assertEqual(response.url, 'https://checkout.stripe.test/cs_g')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__non_owner_staff_rejected_with_the_owners_name(self):
        """POST from staff who are not the deck owner starts nothing: no Stripe
        call, a redirect back with an error naming who CAN act (the server-side
        guard behind the disabled button; maintainer request, 2026-08-09)."""
        self.client.force_login(self.staff)
        with patch('tenant.billing.stripe.checkout.Session.create') as mock_create:
            response = self.client.post(reverse('decks:subscription'), follow=True)
        mock_create.assert_not_called()
        self.assertContains(
            response, f'Only the deck owner, {self.owner.get_username()}, can manage the subscription.'
        )

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_post__stripe_error_redirects_back_with_message(self):
        """A Stripe API failure lands back on the page with a friendly error, not a 500."""
        import stripe as stripe_lib

        with patch('tenant.billing.stripe.checkout.Session.create',
                   side_effect=stripe_lib.StripeError('boom')):
            response = self.client.post(reverse('decks:subscription'), follow=True)
        # No apostrophe in the needle: messages are escaped now, so it arrives as an entity.
        self.assertContains(response, "be reached")

    def test_activating_page__renders_for_staff_with_polling_script(self):
        """The post-checkout page renders the activating message and polls the
        status endpoint."""
        response = self.assert200('decks:subscription_activating')
        self.assertContains(response, 'Activating your subscription')
        self.assertContains(response, reverse('decks:subscription_status'))
        # polling is capped so an abandoned checkout can't hammer Stripe forever
        self.assertContains(response, 'MAX_ATTEMPTS')
        self.assertContains(response, 'poll-timeout-message')

    def test_status__reports_current_subscription_state_without_session(self):
        """Without a session_id the endpoint just reports the deck's derived status."""
        from datetime import timedelta

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=None, paid_until=None)
        response = self.client.get(reverse('decks:subscription_status'))
        self.assertEqual(response.json(), {'active': False})

        self.set_deck(paid_until=localdate() + timedelta(days=100))
        response = self.client.get(reverse('decks:subscription_status'))
        self.assertEqual(response.json(), {'active': True})

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_status__reconciles_completed_checkout_session(self):
        """With a session_id and a completed checkout, the poll links the deck
        (customer + subscription ids), advances paid_until to the subscription's
        period end, and reports active."""
        from datetime import datetime, timedelta, timezone as dt_timezone

        from django.utils.timezone import localdate

        self.set_deck(trial_end_date=None, paid_until=None)
        period_end = datetime.now(tz=dt_timezone.utc) + timedelta(days=365)
        session = {
            'status': 'complete',
            'client_reference_id': self.tenant.schema_name,
            'customer': 'cus_123',
            'subscription': {'id': 'sub_123', 'status': 'active', 'current_period_end': int(period_end.timestamp())},
        }
        with patch('tenant.billing.stripe.checkout.Session.retrieve', return_value=session) as mock_retrieve:
            response = self.client.get(reverse('decks:subscription_status') + '?session_id=cs_123')
        self.assertEqual(response.json(), {'active': True})
        self.assertEqual(mock_retrieve.call_args.args[0], 'cs_123')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_123')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_123')
        self.assertGreater(self.tenant.paid_until, localdate() + timedelta(days=300))

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_status__incomplete_session_and_stripe_errors_stay_inactive(self):
        """An open (unpaid) session, or a Stripe hiccup, leaves the deck untouched
        and reports active=False so the page just keeps polling."""
        import stripe as stripe_lib

        self.set_deck(trial_end_date=None, paid_until=None)
        with patch('tenant.billing.stripe.checkout.Session.retrieve',
                   return_value={'status': 'open', 'client_reference_id': self.tenant.schema_name, 'subscription': None}):
            response = self.client.get(reverse('decks:subscription_status') + '?session_id=cs_123')
        self.assertEqual(response.json(), {'active': False})

        with patch('tenant.billing.stripe.checkout.Session.retrieve',
                   side_effect=stripe_lib.StripeError('down')):
            response = self.client.get(reverse('decks:subscription_status') + '?session_id=cs_123')
        self.assertEqual(response.json(), {'active': False})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, '')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_status__foreign_deck_session_never_links(self):
        """A completed session belonging to a DIFFERENT deck (the session id is
        user-controlled query input) must not write its Stripe ids onto this tenant."""
        self.set_deck(trial_end_date=None, paid_until=None)
        session = {
            'status': 'complete',
            'client_reference_id': 'some_other_deck',
            'metadata': {'schema_name': 'some_other_deck'},
            'customer': 'cus_foreign',
            'subscription': {'id': 'sub_foreign', 'status': 'active'},
        }
        with patch('tenant.billing.stripe.checkout.Session.retrieve', return_value=session):
            response = self.client.get(reverse('decks:subscription_status') + '?session_id=cs_foreign')
        self.assertEqual(response.json(), {'active': False})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, '')
        self.assertEqual(self.tenant.stripe_subscription_id, '')

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_status__incomplete_subscription_not_activated(self):
        """A complete session whose subscription is still 'incomplete' (e.g. failed
        3DS on the first payment) must not grant access."""
        self.set_deck(trial_end_date=None, paid_until=None)
        session = {
            'status': 'complete',
            'client_reference_id': self.tenant.schema_name,
            'customer': 'cus_123',
            'subscription': {'id': 'sub_123', 'status': 'incomplete'},
        }
        with patch('tenant.billing.stripe.checkout.Session.retrieve', return_value=session):
            response = self.client.get(reverse('decks:subscription_status') + '?session_id=cs_123')
        self.assertEqual(response.json(), {'active': False})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, '')


class StripeWebhookViewTest(ByteDeckTenantTestCase):
    """Tests for the Stripe webhook endpoint (epic #1729 PR 7, plan §5.2).

    The endpoint is public-schema-only, so these tests build the public tenant
    (as TenantCreateViewTest does) and POST against it. Signature verification is
    mocked at the SDK seam -- its real crypto is Stripe's to test.
    """

    @classmethod
    def setUpTestData(cls):
        """Build the public schema on the 'testserver' domain."""
        cls.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(cls.public_tenant):
            Tenant.objects.bulk_create([cls.public_tenant])
            cls.public_tenant.refresh_from_db()
            cls.public_tenant.domains.create(domain="testserver", is_primary=True)

    def setUp(self):
        """Keep the default tenant client (super) and add a public-host client."""
        super().setUp()
        self.public_client = TenantClient(self.public_tenant, host="testserver")

    def post_webhook(self, **kwargs):
        """POST an (empty) payload to the webhook with a dummy signature header."""
        return self.public_client.post(
            reverse('decks:stripe_webhook'), data=b'{}', content_type='application/json',
            headers={'stripe-signature': 't=1,v1=dummy'}, **kwargs,
        )

    def test_webhook__503_when_secret_not_configured(self):
        """Without STRIPE_WEBHOOK_SECRET the endpoint refuses (nothing to verify with)."""
        self.assertEqual(self.post_webhook().status_code, 503)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_123')
    def test_webhook__400_on_bad_signature_before_any_db_work(self):
        """An unverifiable payload fails fast with 400 -- unknown-host probes reach
        this endpoint (SHOW_PUBLIC_IF_NO_TENANT_FOUND), so no DB work happens first."""
        import stripe as stripe_lib

        from tenant.models import StripeEventLog

        with patch('stripe.Webhook.construct_event',
                   side_effect=stripe_lib.SignatureVerificationError('bad', 'sig')):
            response = self.post_webhook()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StripeEventLog.objects.exists())

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_123')
    def test_webhook__dispatches_verified_event_and_logs_it(self):
        """A verified event is logged (with its resolved deck) and dispatched once;
        a duplicate delivery is acknowledged without re-running the handler."""
        from tenant.models import StripeEventLog

        event = {'id': 'evt_hook', 'type': 'customer.subscription.updated',
                 'data': {'object': {'id': 'sub_hook', 'status': 'active', 'customer': 'cus_hook',
                                     'metadata': {'schema_name': self.tenant.schema_name}}}}
        with patch('stripe.Webhook.construct_event', return_value=event):
            response = self.post_webhook()
            self.assertEqual(response.status_code, 200)
            log = StripeEventLog.objects.get(event_id='evt_hook')
            self.assertEqual(log.event_type, 'customer.subscription.updated')
            self.assertEqual(log.schema_name, self.tenant.schema_name)

            with patch('tenant.billing.handle_webhook_event') as mock_handler:
                response = self.post_webhook()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'duplicate', response.content)
        mock_handler.assert_not_called()
        self.assertEqual(StripeEventLog.objects.count(), 1)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_123')
    def test_webhook__handles_the_sdks_real_event_object(self):
        """construct_event returns the SDK's Event object, which is NOT a dict on
        stripe-python 15.x (.get() raises AttributeError): the first real staging
        delivery 500ed on every event while tests passed with plain-dict doubles
        (2026-08-09). This pins the seam with the SDK's actual object type."""
        import stripe as stripe_lib

        from tenant.models import StripeEventLog

        payload = {'id': 'evt_sdk', 'type': 'customer.subscription.updated',
                   'data': {'object': {'id': 'sub_sdk', 'status': 'active', 'customer': 'cus_sdk',
                                       'metadata': {'schema_name': self.tenant.schema_name},
                                       'items': {'data': [{'price': {'id': 'price_x', 'metadata': {}}}]}}}}
        sdk_event = stripe_lib.Event.construct_from(payload, 'sk_test_x')
        self.assertFalse(hasattr(sdk_event, 'get'))  # the very property that broke staging

        with patch('stripe.Webhook.construct_event', return_value=sdk_event):
            response = self.post_webhook()

        self.assertEqual(response.status_code, 200)
        log = StripeEventLog.objects.get(event_id='evt_sdk')
        self.assertEqual(log.event_type, 'customer.subscription.updated')
        self.assertEqual(log.schema_name, self.tenant.schema_name)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_123')
    def test_webhook__404_on_tenant_schemas(self):
        """The endpoint only exists on the public schema (public_only_view)."""
        tenant_client = TenantClient(self.tenant)  # requests on the deck's own domain
        response = tenant_client.post(
            reverse('decks:stripe_webhook'), data=b'{}', content_type='application/json')
        self.assertEqual(response.status_code, 404)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_123')
    def test_webhook__handler_crash_rolls_back_event_log_so_stripe_retries(self):
        """A handler crash returns 500 and rolls the StripeEventLog row back with the
        transaction, so Stripe's retry of the event is re-processed, not absorbed
        as a duplicate."""
        from tenant.models import StripeEventLog

        event = {'id': 'evt_crash', 'type': 'customer.subscription.updated',
                 'data': {'object': {'id': 'sub_crash'}}}
        # surface the 500 as a response instead of re-raising into the test
        self.public_client.raise_request_exception = False
        with patch('stripe.Webhook.construct_event', return_value=event):
            with patch('tenant.billing.handle_webhook_event', side_effect=RuntimeError('handler boom')):
                response = self.post_webhook()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(StripeEventLog.objects.filter(event_id='evt_crash').exists())
