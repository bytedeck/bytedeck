# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.commands import loaddata
from django.test import TestCase

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.utils import tenant_context

from tenant.models import Tenant
from tenant.admin import TenantAdmin


class NonPublicTenantAdminTest(TenantTestCase):
    """For testing non-public tenants

    TenantTestCase comes with a `self.tenant`
    
    From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase. 
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and 
        make it available at `self.tenant`

    """

    def test_nonpublic_tenant_admin_save_model(self):
        tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())

        # Can't create tenant outside the `public` schema. Current schema is `test`, so should throw exception
        with self.assertRaises(Exception):
            tenant_model_admin.save_model(obj=Tenant(), request=None, form=None, change=None)


class PublicTenantTestAdminPublic(TestCase):
    """ For testing the `public` tenant. Use normal TestCase base class because we want to 
    test outside of the  tenant architecture
    """

    # fixtures = ['tenants.json']
    # ^ That doesn't work, maybe because tenants isn't in the installed apps list, so it doesn't search this app for fixtures
    # So load fixtures manually

    # Don't use setup because we don't want to load fixtures every time and it doesn't seem to work anyway
    # So initialize some data as class variables that will be persistant through all tests.
    call_command(loaddata.Command(), 'src/tenant/fixtures/tenants.json', verbosity=0)
    tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())
    public_tenant = Tenant.objects.get(schema_name="public")

    def setUp(self):
        pass

    def test_public_tenant_exists(self):
        self.assertIsInstance(self.public_tenant, Tenant)
        self.assertEqual(self.public_tenant.domain_url, "localhost")

    def test_public_tenant_admin_save_model(self):
        non_public_tenant = Tenant(name="Non-Public")
        # public tenant should be able to create new tenant/schemas
        self.tenant_model_admin.save_model(obj=non_public_tenant, request=None, form=None, change=None)
        self.assertIsInstance(non_public_tenant, Tenant)
        # schema names should be all lower case and dashes converted to underscores
        self.assertEqual(non_public_tenant.schema_name, "non_public")

        # switch back to public tenant (why does it switch to non_public we just created?)
        with tenant_context(self.public_tenant):
            # tenant names with spaces should be rejected:
            with self.assertRaises(ValidationError):
                non_public_tenant_bad_name = Tenant(name="Non Public")
                self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
            # also other alpha-numeric characters except dashes and underscores
            with self.assertRaises(ValidationError):
                non_public_tenant_bad_name = Tenant(name="Non*Public")
                self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
