from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from django_tenants.utils import get_public_schema_name, schema_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.utils import deck_cache_key, get_current_deck, get_public_subscribe_url


class GetCurrentDeckTest(ByteDeckTenantTestCase):
    """Tests for the cached per-schema Tenant accessor behind the status banner (epic #1729 PR 3)."""

    def setUp(self):
        """Clear this schema's deck cache -- the cache backend outlives the per-test transaction."""
        cache.delete(deck_cache_key(self.tenant.schema_name))

    def test_get_current_deck__returns_this_schemas_tenant(self):
        """Inside a deck's schema, the accessor returns that deck's Tenant row."""
        deck = get_current_deck()
        self.assertIsNotNone(deck)
        self.assertEqual(deck.schema_name, self.tenant.schema_name)

    def test_get_current_deck__none_on_public_schema(self):
        """The public schema is not a deck, so the accessor returns None there."""
        with schema_context(get_public_schema_name()):
            self.assertIsNone(get_current_deck())

    def test_get_current_deck__none_on_library_schema(self):
        """The shared-library schema is not a billable deck, so the accessor returns None
        there without touching the cache or database."""
        from unittest.mock import patch

        with patch('library.utils.get_library_schema_name', return_value=self.tenant.schema_name):
            self.assertIsNone(get_current_deck())

    def test_get_current_deck__none_when_schema_has_no_tenant_row(self):
        """A schema with no matching Tenant row (e.g. an orphaned schema left by a
        deleted deck) yields None, and nothing gets cached for it."""
        with schema_context('orphanschema'):
            self.assertIsNone(get_current_deck())
        self.assertIsNone(cache.get(deck_cache_key('orphanschema')))

    def test_get_current_deck__caches_and_invalidates_on_save(self):
        """The row is served from cache until a Tenant save invalidates it."""
        get_current_deck()  # prime the cache
        self.assertIsNotNone(cache.get(deck_cache_key(self.tenant.schema_name)))

        # a warm cache serves the row without touching the database
        with self.assertNumQueries(0):
            self.assertEqual(get_current_deck().schema_name, self.tenant.schema_name)

        # a change persisted via save() (signal fires) becomes visible immediately
        self.tenant.max_active_users = 42
        self.tenant.save()
        self.assertIsNone(cache.get(deck_cache_key(self.tenant.schema_name)))
        self.assertEqual(get_current_deck().max_active_users, 42)

    # The test settings replace the cache with a plain LocMem one, dropping the
    # schema-prefixing KEY_FUNCTION that production uses -- restore it here or
    # this test cannot reproduce the cross-schema invalidation bug it pins.
    @override_settings(CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tenant-prefixed-test',
            'KEY_FUNCTION': 'django_tenants.cache.make_key',
            'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key',
        }
    })
    def test_get_current_deck__invalidated_by_save_from_public_schema(self):
        """A Tenant save from the PUBLIC schema (admin edits, future Stripe syncs)
        must invalidate the deck's cached row despite the schema-prefixed cache
        keys (django_tenants KEY_FUNCTION) -- fails without the schema_context
        wrap in invalidate_current_deck_cache."""
        get_current_deck()  # prime the cache from inside the tenant schema

        with schema_context(get_public_schema_name()):
            self.tenant.max_active_users = 77
            self.tenant.save()

        self.assertEqual(get_current_deck().max_active_users, 77)


class GetPublicSubscribeUrlTest(SimpleTestCase):
    """Tests for the absolute public subscribe URL used by the status banner.

    Flatpages are per-schema, so the banner must never link a schema-relative
    /pages/subscribe/ (it would 404 on deck subdomains).
    """

    @override_settings(ROOT_DOMAIN='localhost')
    def test_get_public_subscribe_url__development(self):
        """On a localhost deployment the URL uses http and the dev port."""
        self.assertEqual(get_public_subscribe_url(), 'http://localhost:8000/pages/subscribe/')

    @override_settings(ROOT_DOMAIN='bytedeck.com')
    def test_get_public_subscribe_url__production(self):
        """On a real domain the URL uses https with no port."""
        self.assertEqual(get_public_subscribe_url(), 'https://bytedeck.com/pages/subscribe/')


class WelcomeEmailTest(ByteDeckTenantTestCase):
    """Tests for the new-deck welcome email (deck-request flow polish, 2026-08-08)."""

    def test_send_welcome_email__html_body_and_domain_only_subject(self):
        """The welcome email is a real HTML message (credential list, clickable deck
        link, the logo sigblock) whose subject names just the deck's domain: the
        old subject rendered the Tenant string, which says "name - domain" and so
        repeated the same identifier twice. send_email_message derives the
        plain-text part from the HTML, so both email clients get a formatted
        message instead of one collapsed line."""
        from unittest.mock import patch

        from django.contrib.auth import get_user_model

        from model_bakery import baker

        from tenant.utils import DeckRequestService

        user = baker.make(get_user_model(), first_name='Jane', last_name='Doe', email='jane@example.com')
        with patch('tenant.utils.send_email_message.apply_async') as mock_apply:
            DeckRequestService.send_welcome_email(user, self.tenant, 'pw-secret-123')

        subject, message, recipients = mock_apply.call_args.kwargs['args']
        self.assertEqual(subject, f'Instructions to sign in to {self.tenant.primary_domain_url}')
        self.assertNotIn(' - ', subject)  # the redundant "name - domain" Tenant string is gone
        self.assertEqual(recipients, ['jane@example.com'])
        self.assertIn('<p>Hello Jane Doe,</p>', message)
        self.assertIn(f'<a href="{self.tenant.get_root_url()}">', message)
        self.assertIn('password: <strong>pw-secret-123</strong>', message)
        self.assertIn('change your password', message)
        self.assertIn('alt="[Logo]"', message)  # the standard sigblock, logo included

    def test_send_welcome_email__sigblock_shows_the_wordmark_at_half_size(self):
        """The welcome sigblock logo is the platform wordmark by ABSOLUTE URL at
        half its natural size (maintainer request, 2026-08-08). A new deck's
        SiteConfig only holds the seeded default logo as a schema-relative path,
        which mail clients render as a broken image."""
        from unittest.mock import patch

        from django.contrib.auth import get_user_model
        from django.test import override_settings

        from model_bakery import baker

        from tenant.utils import DeckRequestService

        user = baker.make(get_user_model(), first_name='Jane', last_name='Doe', email='jane@example.com')
        with override_settings(PUBLIC_EMAIL_LOGO_URL='https://cdn.example.com/wordmark.png'):
            with patch('tenant.utils.send_email_message.apply_async') as mock_apply:
                DeckRequestService.send_welcome_email(user, self.tenant, 'pw-secret-123')

        _subject, message, _recipients = mock_apply.call_args.kwargs['args']
        self.assertIn('src="https://cdn.example.com/wordmark.png" width="255" height="64"', message)
        self.assertNotIn('src="/static/', message)  # no schema-relative logo path survives

    def test_send_welcome_email__uses_username_when_owner_name_is_blank(self):
        """An owner with no first/last name set is greeted by username instead of
        an empty "Hello ,": legacy and seeded owners often have no name."""
        from unittest.mock import patch

        from django.contrib.auth import get_user_model

        from model_bakery import baker

        from tenant.utils import DeckRequestService

        user = baker.make(
            get_user_model(), username='nameless-owner', first_name='', last_name='',
            email='nameless@example.com')
        with patch('tenant.utils.send_email_message.apply_async') as mock_apply:
            DeckRequestService.send_welcome_email(user, self.tenant, 'pw-secret-123')

        _subject, message, _recipients = mock_apply.call_args.kwargs['args']
        self.assertIn('<p>Hello nameless-owner,</p>', message)
