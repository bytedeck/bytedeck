from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase

from django_tenants.utils import get_public_schema_name

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from tenant.models import Tenant
from tenant.signals import deck_subdomain, initialize_tenant_with_data, tenant_save_callback


class InitializeTenantWithDataTest(ByteDeckTenantTestCase):
    """Tests for the `post_schema_sync` handler that seeds a new tenant's schema."""

    @patch("tenant.signals.load_initial_tenant_data")
    def test_initialize_tenant_with_data__restores_previous_schema(self, mock_load):
        """The handler seeds the new tenant's schema and then restores the schema
        it started in.

        It previously called ``connection.set_tenant(tenant)`` without switching
        back, leaving the connection on the new tenant for the rest of the
        request. Since deck creation is served from the public schema, the later
        session write then hit the new schema's empty ``django_session`` table and
        raised ``SessionInterrupted``. (``load_initial_tenant_data`` is mocked so
        the test exercises only the schema handling, not the slow data seeding.)
        """
        tenant = Tenant.get()  # the current (non-public) test tenant

        # Simulate a request being served from the public schema (as the deck
        # creation view is) at the moment a new tenant is saved.
        connection.set_schema_to_public()
        try:
            initialize_tenant_with_data(sender=Tenant, tenant=tenant)
            # the connection must be back on the public schema, not left pointed
            # at the tenant the handler just seeded
            self.assertEqual(connection.schema_name, get_public_schema_name())
        finally:
            # restore the test schema for the remainder of the test / teardown
            connection.set_tenant(tenant)

        mock_load.assert_called_once()


class TenantSaveCallbackTest(ByteDeckTenantTestCase):
    """Tests for the `post_save` handler that gives a Tenant its first domain."""

    def test_tenant_save_callback__public_schema_uses_root_domain(self):
        """For the public tenant (which has no subdomain) the created domain is ROOT_DOMAIN
        itself, unlike a regular deck, whose domain is its subdomain then ROOT_DOMAIN.

        A MagicMock stands in for the Tenant so the real public tenant's domains aren't
        mutated: the handler only reads schema_name and calls domains.exists()/create().
        """
        instance = MagicMock()
        instance.schema_name = get_public_schema_name()
        instance.domains.exists.return_value = False  # force the domain-creating path

        tenant_save_callback(sender=Tenant, instance=instance)

        instance.domains.create.assert_called_once_with(domain=settings.ROOT_DOMAIN, is_primary=True)

    def _saved_deck(self, schema_name, name):
        """Run the handler for a new deck with this schema name and name, and return the mock.

        Args:
            schema_name (str): the deck's schema name.
            name (str): the deck's name.

        Returns:
            MagicMock: the stand-in Tenant, whose ``domains.create`` records the domain made.
        """
        instance = MagicMock()
        instance.schema_name = schema_name
        instance.name = name
        instance.domains.exists.return_value = False
        tenant_save_callback(sender=Tenant, instance=instance)
        return instance

    def test_tenant_save_callback__a_deck_domain_is_built_from_its_schema_name(self):
        """A deck's domain comes from its schema name, whatever its name says (#2404).

        The Shared Library is the real case: initdb names it 'Shared Library', and a domain
        built from that name has a space in it, so no browser could ever reach the deck. Built
        from its schema name, `library`, it is the domain the deck is meant to answer on.
        """
        instance = self._saved_deck(schema_name="library", name="Shared Library")

        instance.domains.create.assert_called_once_with(domain=f"library.{settings.ROOT_DOMAIN}", is_primary=True)

    def test_tenant_save_callback__a_dashed_name_keeps_its_subdomain(self):
        """A deck named with dashes is still served at its name (#2404).

        generate_schema_name() turns the dashes of `my-deck` into the schema `my_deck`, and a
        hostname cannot hold an underscore, so they are turned back: the deck-request form
        promises `my-deck.<ROOT_DOMAIN>`, and that is the domain the deck gets.
        """
        instance = self._saved_deck(schema_name="my_deck", name="my-deck")

        instance.domains.create.assert_called_once_with(domain=f"my-deck.{settings.ROOT_DOMAIN}", is_primary=True)


class DeckSubdomainTest(SimpleTestCase):
    """Tests for `deck_subdomain`, which turns a schema name into a subdomain (#2404)."""

    def test_deck_subdomain__makes_any_schema_name_a_hostname(self):
        """A schema made from free text still gives a subdomain a browser can request.

        A Tenant saved with only a name gets `generate_schema_name(name)` as its schema, which
        lower-cases a free-text name but keeps its spaces and accents. The subdomain keeps only
        letters, digits and dashes.
        """
        self.assertEqual(deck_subdomain("hackerspace"), "hackerspace")
        self.assertEqual(deck_subdomain("my_deck"), "my-deck")
        self.assertEqual(deck_subdomain("robotics club"), "robotics-club")
        self.assertEqual(deck_subdomain("café_club"), "cafe-club")
