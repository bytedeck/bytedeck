from allauth.account.adapter import DefaultAccountAdapter

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):

    def clean_username(self, username, shallow=False):
        username = super().clean_username(username, shallow)
        return username.lower()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)

        # Attempt to merge accounts with the same email used in their social account
        if not sociallogin.is_existing:
            try:
                user = User.objects.get(email=sociallogin.user.email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass
