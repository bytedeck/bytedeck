from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection

from django_tenants.utils import get_public_schema_name

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data, tenant_save_callback


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
        """For the public tenant (which has no `<name>.` subdomain) the created domain is
        ROOT_DOMAIN itself, unlike a regular deck whose domain is `<name>.ROOT_DOMAIN`.

        A MagicMock stands in for the Tenant so the real public tenant's domains aren't
        mutated: the handler only reads schema_name and calls domains.exists()/create().
        """
        instance = MagicMock()
        instance.schema_name = get_public_schema_name()
        instance.domains.exists.return_value = False  # force the domain-creating path

        tenant_save_callback(sender=Tenant, instance=instance)

        instance.domains.create.assert_called_once_with(domain=settings.ROOT_DOMAIN, is_primary=True)
