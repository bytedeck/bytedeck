from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from django_tenants.test.cases import TenantTestCase

from tenant.models import Tenant, check_tenant_name, Domain

User = get_user_model()


class TenantModelTest(TenantTestCase):

    def setUp(self):
        # TenantTestCase comes with a `self.tenant` already, but let make another so we can test development
        # stuff on localhost domain
        with Tenant(schema_name='public'):
            self.tenant_localhost = Tenant.objects.create(
                schema_name='my_development_schema',
                name='my_name'
            )
        domain = Domain.objects.create(domain='my-dev-schema.localhost', tenant=self.tenant_localhost)
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


class CheckTenantNameTest(SimpleTestCase):
    """ A tenant's name is used for both the schema_name and as the subdomain in the 
    tenant's domain_url field, so {name} it must be valid for a schema and a url.
    """

    def test_underscore_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, 'tenant_name_with_underscores')

    def test_special_chars_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, 'tenant@')

    def test_number_start_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, '9tenant')      

    def test_uppercase_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, 'Tenant')     

    def test_start_dash_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, '-tenant')  
    
    def test_end_dash_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, 'tenant-')  

    def test_multidash_invalid(self):
        self.assertRaises(ValidationError, check_tenant_name, 'ten--ant')  
    
    def test_mid_dash_valid(self):
        check_tenant_name('ten-ant')  

    def test_multi_mid_dash_valid(self):
        check_tenant_name('ten-an-t')

    def test_mid_number_valid(self):
        check_tenant_name('t3nan4') 
