from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.shortcuts import reverse
from django.utils.timezone import localdate

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from tenant.middleware import SUSPENDED_SIGN_OUT_MESSAGE
from tenant.utils import deck_cache_key

User = get_user_model()


class OwnerOnlyWhenSuspendedMiddlewareTest(ByteDeckTenantTestCase):
    """Behavioral tests for the suspension sign-in policy (#1734 redesign): on a
    suspended deck only the deck owner (and the ByteDeck support admin) can stay
    signed in; everyone else is signed out at request time, whatever session
    they were already holding."""

    def setUp(self):
        """Build per-role users and clear the cached deck row (the cache backend
        outlives each test's transaction)."""
        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.staff = baker.make(User, is_staff=True)
        self.student = baker.make(User)
        self.owner = SiteConfig.get().deck_owner

    def set_deck(self, **fields):
        """Persist billing fields on this deck via save() so the cache invalidates."""
        for name, value in fields.items():
            setattr(self.tenant, name, value)
        self.tenant.save()

    def suspend_deck(self):
        """Put this deck into the suspended state (trial lapsed, no subscription)."""
        self.set_deck(trial_end_date=date(2020, 1, 1), paid_until=None)

    def get_quests_page(self, user):
        """Return the quest-list page as the given user (a page every role can load)."""
        self.client.force_login(user)
        return self.client.get(reverse('quests:quests'))

    def test_bounce__non_owner_is_signed_out_and_redirected_with_message(self):
        """A signed-in teacher on a suspended deck is bounced: redirected to the
        sign-in page, session ended, and told why via a message. Students get
        exactly the same treatment."""
        self.suspend_deck()
        for user in (self.staff, self.student):
            response = self.get_quests_page(user)
            # don't fetch the target here: rendering the sign-in page consumes the message
            self.assertRedirects(response, reverse('account_login'), fetch_redirect_response=False)
            follow = self.client.get(reverse('account_login'))
            self.assertContains(follow, SUSPENDED_SIGN_OUT_MESSAGE)
            # the session is really gone: the next request is anonymous
            self.assertFalse(follow.wsgi_request.user.is_authenticated)

    def test_bounce__owner_and_support_admin_keep_access(self):
        """The deck owner and the ByteDeck support account are exempt: both still
        load pages normally on a suspended deck."""
        self.suspend_deck()
        support_admin, _ = User.objects.get_or_create(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        for user in (self.owner, support_admin):
            response = self.get_quests_page(user)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_bounce__anonymous_visitors_are_untouched(self):
        """Anonymous requests pass through: the sign-in page renders normally on a
        suspended deck (with the suspended status banner, no redirect loop)."""
        self.suspend_deck()
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This deck is suspended')

    def test_bounce__nobody_bounced_while_not_suspended(self):
        """On a live deck (trial running, or paid, or in grace) nobody is bounced.
        A lapsed trial's grace window counts (#1734 B4): students keep access for
        the full grace period before the owner-only bounce begins."""
        for fields in (
            {'trial_end_date': localdate() + timedelta(days=30), 'paid_until': None},  # on trial
            {'trial_end_date': None, 'paid_until': localdate() + timedelta(days=30)},  # subscribed
            {'trial_end_date': None, 'paid_until': localdate() - timedelta(days=5)},   # in paid grace
            {'trial_end_date': localdate() - timedelta(days=5), 'paid_until': None},   # in trial grace (#1734 B4)
        ):
            self.set_deck(**fields)
            for user in (self.staff, self.student, self.owner):
                self.assertEqual(self.get_quests_page(user).status_code, 200)

    def test_bounce__comped_deck_is_never_suspended(self):
        """A deck with both date fields blank (comped/managed manually) never
        suspends, so nobody is bounced."""
        self.set_deck(trial_end_date=None, paid_until=None)
        self.assertEqual(self.get_quests_page(self.staff).status_code, 200)

    def test_bounce__non_deck_schemas_pass_through(self):
        """On the public and shared-library schemas get_current_deck() returns
        None (they are not billable decks), so authenticated requests pass
        through to the view untouched, never redirected to login."""
        from unittest.mock import patch

        from django.http import HttpResponse
        from django.test import RequestFactory

        from tenant.middleware import OwnerOnlyWhenSuspendedMiddleware

        middleware = OwnerOnlyWhenSuspendedMiddleware(lambda request: HttpResponse('view ran'))
        request = RequestFactory().get('/')
        request.user = self.staff  # authenticated, and not any deck's owner
        with patch('tenant.middleware.get_current_deck', return_value=None):
            response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'view ran')
