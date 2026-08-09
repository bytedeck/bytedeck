from django_tenants.utils import get_public_schema_name, schema_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.templatetags.tenant_tags import _is_public_schema, is_public_schema


class TenantTagsPublicSchemaTest(ByteDeckTenantTestCase):
    """Tests for the is_public_schema / _is_public_schema template helpers.

    ByteDeckTenantTestCase runs on a non-public ('test') schema, so the default is False; the
    public case is exercised inside a schema_context(public).
    """

    def test_is_public_schema__false_on_non_public_tenant(self):
        """On a regular tenant schema both helpers report False."""
        self.assertFalse(is_public_schema())
        self.assertFalse(_is_public_schema())

    def test_is_public_schema__true_on_public_schema(self):
        """Inside the public schema both helpers report True."""
        with schema_context(get_public_schema_name()):
            self.assertTrue(is_public_schema())
            self.assertTrue(_is_public_schema())
