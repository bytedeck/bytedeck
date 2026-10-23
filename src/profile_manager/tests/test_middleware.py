"""Tests for profile_manager's middleware."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from profile_manager.middleware import LAST_ACTIVE_SESSION_KEY, LastActiveMiddleware

User = get_user_model()


class LastActiveMiddlewareTest(ByteDeckTenantTestCase):
    """Recording when a person last used their deck (#2849)."""

    def setUp(self):
        """Sign in a student."""
        self.student = User.objects.create_user('active_student')
        self.client.force_login(self.student)

    def _last_active(self):
        """The student's last activity, as stored.

        Returns:
            datetime or None: `Profile.last_active`.
        """
        self.student.profile.refresh_from_db()
        return self.student.profile.last_active

    def test_last_active__a_page_records_the_time(self):
        """Opening a page records when the student was there."""
        before = timezone.now()
        self.client.get(reverse('quests:quests'))
        self.assertGreaterEqual(self._last_active(), before)
        self.assertIn(LAST_ACTIVE_SESSION_KEY, self.client.session)

    def test_last_active__recorded_at_most_once_an_hour(self):
        """Within the hour of the last record the time stays put; after it, the next page
        records it again."""
        start = timezone.now()
        with patch('profile_manager.middleware.timezone.now', return_value=start):
            self.client.get(reverse('quests:quests'))
        with patch('profile_manager.middleware.timezone.now', return_value=start + timedelta(minutes=59)):
            self.client.get(reverse('quests:quests'))
        self.assertEqual(self._last_active(), start)

        later = start + timedelta(minutes=61)
        with patch('profile_manager.middleware.timezone.now', return_value=later):
            self.client.get(reverse('quests:quests'))
        self.assertEqual(self._last_active(), later)

    def test_last_active__not_from_the_badges_refreshing_themselves(self):
        """An open page refreshes the notification and approvals badges on a timer, which isn't
        the person using the deck."""
        self.client.get(reverse('notifications:ajax'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.get(reverse('quests:ajax_submission_count'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertIsNone(self._last_active())

    def test_last_active__nobody_recorded_for_a_visitor_not_signed_in(self):
        """A visitor who isn't signed in has no profile to record on, and the page still loads."""
        self.client.logout()
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._last_active())

    def test_is_due__never_on_the_public_site(self):
        """The public site has no profiles, so nothing is due there; the same request on a deck is."""
        request = RequestFactory().get('/')
        request.user = self.student
        request.session = {}
        with schema_context(get_public_schema_name()):
            self.assertFalse(LastActiveMiddleware.is_due(request))
        self.assertTrue(LastActiveMiddleware.is_due(request))
