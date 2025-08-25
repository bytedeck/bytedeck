import functools

from django.contrib.sites.models import Site
from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from django.http import Http404, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView
from django.views.generic import FormView
from django.urls import reverse_lazy

from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context        # <- unused in this file

from allauth.account.utils import user_username
from allauth.account.models import EmailAddress

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
        # staff always allowed
        if request.user.is_authenticated and request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)

        # allow if session has verified token
        if request.session.get("verified_deck_request"):
            return super().dispatch(request, *args, **kwargs)

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
        if not self.request.user.is_staff:
            # Pass verified deck request from session to the form, if it exists
            verified_data = self.request.session.get("verified_deck_request")
            if verified_data:
                kwargs["verified_data"] = verified_data
        return kwargs

    def get_success_url(self):
        """
        Returns the URL to redirect to after a successful tenant creation.

        Returns:
            str: The root URL of the newly created tenant.
        """
        return self.object.get_root_url()

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
            HttpResponseRedirect: Redirect to the tenant's login page.
        """
        # Copy tenant name to schema_name and domain_url
        form.instance.schema_name = form.instance.name.replace('-', '_')
        form.instance.domain_url = f'{form.instance.name}.{Site.objects.get(id=1).domain}'

        # Save tenant
        self.object = form.save()

        # saved object (tenant) can be accessed via `object` attribute
        cleaned_data = form.cleaned_data
        with tenant_context(self.object):
            owner = SiteConfig.get().deck_owner

            # otherwise save first / last name
            owner.first_name = cleaned_data['first_name']
            owner.last_name = cleaned_data['last_name']
            owner.save()

            # set the owner's username to firstname.lastname (instead of "owner")
            user_username(owner, f"{owner.first_name}.{owner.last_name}")

            # set the owner's password to firstname-deckname-lastname
            owner.set_password(generate_default_owner_password(owner, self.object))

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
                email_address.save()

            DeckRequestService.send_welcome_email(owner, self.object)

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
    success_url = reverse_lazy("decks:request_new_deck")

    def form_valid(self, form):
        """
        Handle valid deck request form submissions.

        Extracts the user's first name, last name, and email from the form.
        Generates a signed verification token and sends an email containing
        the verification link. A success message is displayed prompting the
        user to check their inbox.

        Args:
            form (DeckRequestForm): The validated form instance containing
                the user's information.

        Returns:
            HttpResponse: Redirect to the success URL as defined by FormView.
        """
        first_name = form.cleaned_data["first_name"]
        last_name = form.cleaned_data["last_name"]
        email = form.cleaned_data["email"]

        token = DeckRequestService.generate_token(first_name, last_name, email)
        DeckRequestService.send_verification_email(first_name, email, token, request=self.request)

        messages.success(self.request, "Check your email to verify your request!")
        return super().form_valid(form)


def verify_deck_request(request, token):
    """
    Verify a deck creation request via a signed token.

    Attempts to decode the provided verification token. If valid, the
    decoded data (deck name and user info) is stored in the session under
    `verified_deck_request` so it can be prefilled during deck creation.
    If invalid or expired, an error message is shown and the user is
    redirected back to the request form.

    Args:
        request (HttpRequest): The current request object.
        token (str): The signed token received from the verification email.

    Returns:
        HttpResponseRedirect: Redirects to either the deck request form if
        verification fails, or the deck creation form if verification succeeds.
    """
    data = DeckRequestService.decode_token(token)
    if not data:
        messages.error(
            request,
            "Your verification link is invalid or has expired. "
            "Please request a new deck verification email."
        )
        return redirect("decks:request_new_deck")

    # stash verification in session
    request.session["verified_deck_request"] = data

    messages.success(request, "Email verified! Now create your deck.")

    # redirect to deck creation form
    return redirect("decks:new")
