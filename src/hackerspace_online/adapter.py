from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.shortcuts import redirect
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.utils import build_absolute_uri
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django_tenants.utils import get_tenant_model

from tenant.utils import get_current_deck

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        """No new sign-ups on a suspended deck (#1734 redesign): a suspended deck is
        owner-only, so a brand-new account registering (and landing in a signed-in
        session) contradicts the suspension. allauth renders
        account/signup_closed.html when this returns False, and the social-account
        adapter delegates its own is_open_for_signup here, so this single guard
        covers both the sign-up form and Google sign-ups.

        get_current_deck() is None outside deck schemas (public/library), where
        sign-up stays governed by the default behavior.
        """
        deck = get_current_deck()
        if deck is not None and deck.is_suspended:
            return False
        return super().is_open_for_signup(request)

    def clean_username(self, username, shallow=False):
        username = super().clean_username(username, shallow)
        return username.lower()

    def get_email_confirmation_url(self, request, emailconfirmation):
        """
        Constructs the email confirmation (activation) url.

        *Note* that if you have architected your system such that email
        confirmations are sent outside of the request context `request`
        can be `None` here.
        """
        # clear the ``Site`` object cache
        Site.objects.clear_cache()

        # get current tenant object...
        tenant = get_tenant_model().get()
        # ...and use it to build absolute uri
        location = ''.join((tenant.get_root_url(), reverse("account_confirm_email", args=[emailconfirmation.key])))
        return build_absolute_uri(request=None, location=location)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed
        (and before the pre_social_login signal is emitted).

        ---

        Currently using this to automatically connect a google account
        to an existing user provided that they used the same email address
        for logging in
        """

        super().pre_social_login(request, sociallogin)

        # Check if we can automatically merge a social account to an existing local account if
        # the email address they used is verified.
        # If the email they used is not verified, then redirect them to to merge account page
        if not sociallogin.is_existing:
            try:
                user = User.objects.get(email=sociallogin.user.email)
                verified_email = EmailAddress.objects.filter(verified=True, email=sociallogin.user.email)

                if verified_email.exists():
                    sociallogin.connect(request, user)
                else:
                    # Since there was an email matching user.email but has not been verified,
                    # redirect them to the merge account page
                    # request.session["matching_user_id"] = user.get_username()
                    request.session['merge_with_user_id'] = user.pk

                    # Add these to the session data so we can re-use it during OAuth merge account flow
                    request.session['socialaccount_sociallogin'] = sociallogin.serialize()
                    raise ImmediateHttpResponse(redirect('profiles:oauth_merge_account'))
            except User.DoesNotExist:
                pass
