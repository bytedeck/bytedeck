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
