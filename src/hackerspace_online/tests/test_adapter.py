from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.test import RequestFactory

from hackerspace_online.adapter import CustomSocialAccountAdapter


class CustomSocialAccountAdapterTest(SimpleTestCase):
    """Tests for CustomSocialAccountAdapter.pre_social_login."""

    def test_pre_social_login__existing_login_returns_early(self):
        """When the social login already maps to a local account, the auto-merge block is skipped
        (nothing is connected) and the method returns."""
        sociallogin = MagicMock(is_existing=True)

        result = CustomSocialAccountAdapter().pre_social_login(RequestFactory().get('/'), sociallogin)

        self.assertIsNone(result)
        sociallogin.connect.assert_not_called()
