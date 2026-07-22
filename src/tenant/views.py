import functools
import hashlib

from django.contrib.sites.models import Site
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.db import connection
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.utils import timezone
from django.views.generic.edit import CreateView
from django.views.generic import FormView, TemplateView
from django.urls import reverse_lazy

from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from allauth.account.utils import user_username
from allauth.account.models import EmailAddress

from hackerspace_online.decorators import staff_member_required
from siteconfig.models import SiteConfig

from .forms import TenantForm, DeckRequestForm
from .models import Tenant
from .utils import DeckRequestService, generate_default_owner_password


def public_only_view(f):
    """A decorator that causes a view to raise Http404() if it is accessed by a non-public tenant"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name == get_public_schema_name():
            return f(*args, **kwargs)
        else:
            raise Http404()
    return wrapper


class PublicOnlyViewMixin:
    """A mixin that causes a view to raise Http404() if it is accessed by a non-public tenant"""
    @method_decorator(public_only_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


def non_public_only_view(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name != get_public_schema_name():
            return f(*args, **kwargs)
        raise Http404("Page not found!")
    return wrapper


class NonPublicOnlyViewMixin:

    @method_decorator(non_public_only_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class EmailVerificationRequiredMixin:
    """
    Restricts access to views unless:
    - The user is staff (always allowed), OR
    - The session has a verified_deck_request.

    Does NOT require authentication if the user has a verified_deck_request.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Gate the view on staff status or a recent verified deck request.

        Access is granted (delegating to ``super().dispatch``) when the user is
        authenticated staff, or when the session holds a ``verified_deck_request``
        whose ``verified_at`` timestamp is within ``TOKEN_MAX_AGE``. A stale or
        malformed verification is cleared from the session. Otherwise the request
        is denied with the ``deck_request_denied.html`` template and HTTP 403.

        Args:
            request (HttpRequest): The current request.
            *args: Positional arguments forwarded to the wrapped view.
            **kwargs: Keyword arguments forwarded to the wrapped view.

        Returns:
            HttpResponse: The wrapped view's response when authorized, otherwise
            a 403 response rendering the denial template.
        """
        # staff always allowed
        if request.user.is_authenticated and request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)

        # allow if session has verified token
        verified = request.session.get("verified_deck_request")
        if verified:
            verified_at = verified.get("verified_at")
            if verified_at is not None:
                now_ts = timezone.now().timestamp()
                if now_ts - float(verified_at) <= DeckRequestService.TOKEN_MAX_AGE:
                    return super().dispatch(request, *args, **kwargs)
            # stale or malformed so clear it
            request.session.pop("verified_deck_request", None)

        # deny otherwise
        return render(request, "tenant/deck_request_denied.html", status=403)


class TenantCreate(PublicOnlyViewMixin, EmailVerificationRequiredMixin, CreateView):
    """
    View to create a new tenant (deck) in the system.

    Collects tenant name, owner first and last name, and email.
    Automatically creates or updates the deck owner, sets a default password,
    verifies the owner's email, and sends a welcome email via DeckRequestService.
    """
    model = Tenant
    form_class = TenantForm
    template_name = 'tenant/tenant_form.html'
    login_url = reverse_lazy('admin:login')

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.

        If there is a verified deck request stored in the session, it is
        passed to the form under the 'verified_data' key.

        Returns:
            dict: Form keyword arguments, possibly including 'verified_data'.
        """
        kwargs = super().get_form_kwargs()
        verified_data = self.request.session.get("verified_deck_request")
        kwargs['verified_data'] = verified_data
        return kwargs

    def form_valid(self, form):
        """
        Called when the submitted form is valid.

        Creates the tenant instance and updates the deck owner's information.
        Sets a default password, marks the email as verified, and sends a
        welcome email to the owner. Finally, redirects to the tenant's login
        page with a 'created=1' query parameter.

        Args:
            form (TenantForm): The validated form instance.

        Returns:
            HttpResponseRedirect: Redirect to the tenant's login page, or back to
            the request form if the verification nonce has already been used.
        """
        # Single-use enforcement: consume the verification nonce before doing any
        # work, so one verified request can create at most one deck. Re-opening
        # the link after a deck was already created (or after the nonce expired)
        # lands here with a stale nonce and is rejected. Staff are exempt — they
        # reach this view without an email verification (see
        # EmailVerificationRequiredMixin), so there is no nonce to consume.
        user = getattr(self.request, "user", None)
        is_staff = bool(getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))
        if not is_staff:
            nonce = (self.request.session.get("verified_deck_request") or {}).get("nonce")
            if not DeckRequestService.consume_request(nonce):
                messages.error(
                    self.request,
                    "This deck request has already been used or has expired. "
                    "Please request a new deck verification email."
                )
                self.request.session.pop("verified_deck_request", None)
                return redirect("decks:request_new_deck")

        # Normalize: valid Postgres schema and subdomain
        name_slug = slugify(form.instance.name)
        schema = name_slug.replace("-", "_")[:63]
        if not schema or not schema[0].isalpha():
            schema = f"t_{schema}"[:63]
        form.instance.schema_name = schema
        current_domain = Site.objects.get_current().domain
        form.instance.domain_url = f"{name_slug}.{current_domain}"

        # Save tenant
        self.object = form.save()

        # saved object (tenant) can be accessed via `object` attribute
        cleaned_data = form.cleaned_data
        with tenant_context(self.object):
            owner = SiteConfig.get().deck_owner

            # otherwise save first / last name
            owner.first_name = cleaned_data['first_name']
            owner.last_name = cleaned_data['last_name']

            # set the owner's username to firstname.lastname (instead of "owner")
            user_username(owner, f"{owner.first_name}.{owner.last_name}")

            # generate the initial password once, so the value set here is the
            # same one emailed to the owner in the welcome message
            password = generate_default_owner_password()
            owner.set_password(password)

            # Email is immutable but assign for completeness
            owner.email = cleaned_data.get("email")
            owner.full_clean()
            owner.save()

            # Mark email as verified and primary
            email_address, created = EmailAddress.objects.get_or_create(
                user=owner,
                email=owner.email,
                defaults={'verified': True, 'primary': True}
            )
            if not created:
                email_address.verified = True
                email_address.primary = True
                email_address.full_clean()
                email_address.save()

            DeckRequestService.send_welcome_email(owner, self.object, password)

        login_url = f"{self.object.get_root_url().rstrip('/')}/accounts/login/?created=1"
        # clear the verified deck request so the next visit gets a clean form
        self.request.session.pop("verified_deck_request", None)
        return HttpResponseRedirect(login_url)


class RequestNewDeck(PublicOnlyViewMixin, FormView):
    """
    View to handle requests for creating a new deck.

    Renders a form to collect first name, last name, and email. Upon valid
    submission, it sends a verification email containing a time-limited token
    to confirm the user's email address before creating a new deck.

    Inherits:
        PublicOnlyViewMixin: restricts access to the public schema only.
        FormView: standard Django form handling.
    """

    form_class = DeckRequestForm
    template_name = "tenant/request_new_deck.html"
    # Redirect to a dedicated confirmation page that explains the next steps,
    # instead of dropping the user back on the form with a thin flash banner.
    success_url = reverse_lazy("decks:request_new_deck_submitted")

    def form_valid(self, form):
        """
        Handle valid deck request form submissions.

        Extracts the user's first name, last name, and email from the form.
        Generates a signed verification token and sends an email containing
        the verification link, then redirects to a confirmation page that
        explains the next steps.

        Args:
            form (DeckRequestForm): The validated form instance containing
                the user's information.

        Returns:
            HttpResponse: Redirect to the confirmation page (``success_url``).
        """
        first_name = form.cleaned_data["first_name"]
        last_name = form.cleaned_data["last_name"]
        email = form.cleaned_data["email"]

        # Throttle verification emails per address so this public endpoint can't
        # be used to flood someone's inbox. We always redirect to the same
        # confirmation page regardless of whether an email was actually sent, so
        # the response never reveals whether the address was already in cooldown.
        # The email is hashed into the key so raw addresses aren't exposed in
        # cache tooling, and cache.add() reserves the key atomically so two
        # concurrent requests can't both slip past the check and send twice.
        email_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        throttle_key = f"deck-request-throttle-{email_hash}"
        if cache.add(throttle_key, True, DeckRequestService.REQUEST_COOLDOWN):
            nonce = DeckRequestService.create_request(first_name, last_name, email)
            DeckRequestService.send_verification_email(first_name, email, nonce, request=self.request)

        return super().form_valid(form)


@public_only_view
def verify_deck_request(request, nonce):
    """
    Verify a deck creation request via an opaque, single-use nonce.

    Looks up the requester data stored server-side against the nonce. If found,
    the data (plus the nonce itself) is stashed in the session under
    `verified_deck_request` so it can prefill the deck-creation form and be
    consumed when a deck is actually created. The nonce is deliberately *not*
    consumed here, so re-opening the link before creating a deck still works.
    If the nonce is unknown or expired, an error message is shown and the user
    is redirected back to the request form.

    Args:
        request (HttpRequest): The current request object.
        nonce (str): The opaque nonce received from the verification email.

    Returns:
        HttpResponseRedirect: Redirects to either the deck request form if
        verification fails, or the deck creation form if verification succeeds.
    """
    data = DeckRequestService.peek_request(nonce)
    if not data:
        messages.error(
            request,
            "Your verification link is invalid or has expired. "
            "Please request a new deck verification email."
        )
        return redirect("decks:request_new_deck")

    # stash verification in session; the nonce is carried so it can be consumed
    # (single-use) when the deck is actually created in TenantCreate.form_valid
    request.session["verified_deck_request"] = {
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "email": data.get("email", ""),
        "nonce": nonce,
        "verified_at": timezone.now().timestamp(),
    }

    messages.success(request, "Email verified! Now create your deck.")

    # redirect to deck creation form
    return redirect("decks:new")


def _humanize_seconds(seconds):
    """Render a whole number of seconds as a friendly duration string.

    Used to surface the deck-request timeouts (``TOKEN_MAX_AGE`` /
    ``REQUEST_COOLDOWN``) on the confirmation page from their actual configured
    values, so the on-page copy can't drift. Examples: ``3600 -> "1 hour"``,
    ``300 -> "5 minutes"``, ``90 -> "90 seconds"``.

    Args:
        seconds (int): A non-negative number of seconds.

    Returns:
        str: The duration in the largest whole unit (hours, then minutes, then
        seconds) with correct singular/plural wording.
    """
    for unit_seconds, unit_name in ((3600, "hour"), (60, "minute"), (1, "second")):
        if seconds >= unit_seconds and seconds % unit_seconds == 0:
            value = seconds // unit_seconds
            return f"{value} {unit_name}{'s' if value != 1 else ''}"
    return f"{seconds} seconds"


class RequestNewDeckSubmitted(PublicOnlyViewMixin, TemplateView):
    """Confirmation page shown after a deck request is submitted.

    Replaces the old "check your email" flash message with a full page that
    walks the requester through the onboarding workflow (verify email -> name
    and create the deck -> welcome email with credentials) and states the
    verification-link validity window and resend cooldown.

    The page is static informational content rendered for every valid
    submission, so — like the flash message it replaces — it never reveals
    whether an email was actually sent (see ``RequestNewDeck.form_valid``).
    """

    template_name = "tenant/request_new_deck_submitted.html"

    def get_context_data(self, **kwargs):
        """Surface the deck-request timeouts as friendly strings, derived from
        ``DeckRequestService``'s settings so the on-page copy can't drift from
        the values actually enforced.

        Args:
            **kwargs: Keyword arguments from the URLconf, passed through to the
                base ``TemplateView`` implementation.

        Returns:
            dict: The template context, with ``verification_validity`` and
            ``resend_cooldown`` duration strings added to the base context.
        """
        context = super().get_context_data(**kwargs)
        context["verification_validity"] = _humanize_seconds(DeckRequestService.TOKEN_MAX_AGE)
        context["resend_cooldown"] = _humanize_seconds(DeckRequestService.REQUEST_COOLDOWN)
        return context


class SubscriptionDetail(NonPublicOnlyViewMixin, TemplateView):
    """Staff-facing "Subscription details" page for the current deck (epic #1729 PR 6).

    GET shows the deck's billing status, expiry dates, student-seat usage (live
    count), and the upgrade/renew action. POST starts the Stripe flow: Checkout
    for an unlinked deck, the Billing Portal for a linked one. When Stripe isn't
    configured the page says so and the action falls back to the public
    subscribe page. Linked from the admin menu for all staff.
    """
    template_name = 'tenant/subscription_detail.html'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        """Require staff (non-staff get 403, anonymous get the login redirect)."""
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        """Assemble the deck's billing facts for the template.

        Returns:
            dict: The template context with the current deck, a LIVE
            current-student count (the nightly cached one can be a day old), the
            effective cap, the billing constants the copy references, whether
            Stripe billing is configured, and the public-subscribe fallback URL.
        """
        from .billing import billing_configured
        from .models import GRACE_PERIOD_DAYS, TRIAL_MAX_ACTIVE_USERS
        from .utils import get_public_subscribe_url

        context = super().get_context_data(**kwargs)
        deck = self.request.tenant
        context.update({
            'deck': deck,
            'current_student_count': deck.get_active_user_count(),  # live, not cached
            'cap': deck.effective_max_active_users,
            'trial_cap': TRIAL_MAX_ACTIVE_USERS,
            'grace_days': GRACE_PERIOD_DAYS,
            'stripe_configured': billing_configured(),
            'public_subscribe_url': get_public_subscribe_url(),
        })
        return context

    def post(self, request, *args, **kwargs):
        """Start the Stripe flow: Checkout (unlinked deck) or Billing Portal (linked).

        Returns:
            HttpResponse: A redirect to the Stripe-hosted page, or back to this
            page with an error message when Stripe isn't configured or errors out.
        """
        import stripe as stripe_lib

        from .billing import billing_configured, create_checkout_session, create_portal_session

        deck = request.tenant
        if not billing_configured():
            messages.error(request, "Online billing isn't configured on this server.")
            return redirect('decks:subscription')
        try:
            if deck.stripe_customer_id:
                url = create_portal_session(deck)
            else:
                url = create_checkout_session(deck)
        except stripe_lib.StripeError:
            messages.error(request, "Sorry, Stripe couldn't be reached. Please try again in a few minutes.")
            return redirect('decks:subscription')
        return HttpResponseRedirect(url)


class SubscriptionActivating(NonPublicOnlyViewMixin, TemplateView):
    """The Checkout success page: "activating your subscription..." (epic #1729 PR 6).

    Stripe redirects here with ?session_id=; the page polls the status endpoint
    below, which reconciles against Stripe and reports when the deck is active,
    then this page forwards back to the subscription details. Never assumes a
    webhook landed (plan §5.4) -- the polling reconciliation IS the activation
    path in this PR; webhooks (PR 7) take over renewals later.
    """
    template_name = 'tenant/subscription_activating.html'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        """Require staff, like the subscription page it forwards back to."""
        return super().dispatch(*args, **kwargs)


@non_public_only_view
@staff_member_required
def subscription_status(request):
    """JSON poll target for the activating page: is this deck's subscription live yet?

    When a ``session_id`` is supplied and the deck isn't linked yet, reconciles
    the checkout session against Stripe first (linking the deck and advancing
    paid_until if the session completed). Stripe/API hiccups return active=False
    rather than erroring -- the page just polls again.

    Returns:
        JsonResponse: {"active": bool} for the polling script.
    """
    import stripe as stripe_lib

    from .billing import billing_configured, reconcile_checkout_session

    deck = request.tenant
    session_id = request.GET.get('session_id')
    if session_id and billing_configured() and not deck.stripe_subscription_id:
        try:
            reconcile_checkout_session(deck, session_id)
        except stripe_lib.StripeError:
            pass  # transient; the page polls again in a few seconds
        deck.refresh_from_db()
    return JsonResponse({'active': deck.subscription_active})
