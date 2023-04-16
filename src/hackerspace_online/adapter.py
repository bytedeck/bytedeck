from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.exceptions import ImmediateHttpResponse

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):

    def clean_username(self, username, shallow=False):
        username = super().clean_username(username, shallow)
        return username.lower()


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
