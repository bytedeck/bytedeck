from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase

from tenant.models import Tenant

User = get_user_model()


class TenantTestModel(TenantTestCase):

    def setUp(self):
        # TenantTestCase comes with a `self.tenant` already, but let make another so we can test development
        # stuff on localhost domain
        self.tenant_localhost = Tenant(
            domain_url='my-dev-schema.localhost',
            schema_name='my_development_schema',
            name='my_name'
        )
        pass

    def test_tenant_test_case(self):
        """ From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase. 
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and 
        make it available at `self.tenant`
        """
        self.assertIsInstance(self.tenant, Tenant)
        # self.assertEqual(self.tenant.name, self.tenant.schema_name)
        self.assertEqual(str(self.tenant), '%s - %s' % (self.tenant.schema_name, self.tenant.domain_url))

    def test_tenant_creation(self):
        self.assertIsInstance(self.tenant_localhost, Tenant)

    def test_tenant_get_root_url(self):
        self.assertEqual(self.tenant.get_root_url(), "https://tenant.test.com")
        self.assertEqual(self.tenant_localhost.get_root_url(), "http://my-dev-schema.localhost:8000")
