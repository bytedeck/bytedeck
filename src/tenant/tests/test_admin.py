# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import tenant_context

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


class PublicTenantTestAdminPublic(TenantTestCase):
    """ For testing the `public` tenant. Use normal TestCase base class because we want to 
    test outside of the  tenant architecture
    """
    ###############################################################################
    # Not sure why this doesn't work, but seems like TenantTestCase is 
    # stops using the test databse and is looking for the real databse? or something...
    # So it fails on TravisCI where there is no database names `postgress` 
    ###############################################################################
    # fixtures = ['tenant/tenants.json']

    # # This doesn't seem to work when placed in SetUp, so make them class variables.
    # tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())
    # public_tenant = Tenant.objects.get(schema_name="public")

    # def test_public_tenant_exists(self):
    #     self.assertIsInstance(self.public_tenant, Tenant)
    #     self.assertEqual(self.public_tenant.domain_url, "localhost")
    #################################################################################

    def test_public_tenant_admin_save_model(self):
        # create the public schema first:
        public_tenant = Tenant(
            domain_url='localhost',
            schema_name='public',
            name='public'
        )

        tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())

        with tenant_context(public_tenant):
            non_public_tenant = Tenant(name="Non-Public")
            # public tenant should be able to create new tenant/schemas
            tenant_model_admin.save_model(obj=non_public_tenant, request=None, form=None, change=None)
            self.assertIsInstance(non_public_tenant, Tenant)
            # schema names should be all lower case and dashes converted to underscores
            self.assertEqual(non_public_tenant.schema_name, "non_public")

        # oddly, seems to switch connections to the newly created "non_public" schema
        # so need to set context back to public to test more stuff
        with tenant_context(public_tenant):
            # tenant names with spaces should be rejected:
            with self.assertRaises(ValidationError):
                non_public_tenant_bad_name = Tenant(name="Non Public")
                tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
            # also other alpha-numeric characters except dashes and underscores
            with self.assertRaises(ValidationError):
                non_public_tenant_bad_name = Tenant(name="Non*Public")
                tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
