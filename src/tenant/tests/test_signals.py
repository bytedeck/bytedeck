from unittest.mock import patch

from django.db import connection

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name

from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data


class InitializeTenantWithDataTest(TenantTestCase):
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
