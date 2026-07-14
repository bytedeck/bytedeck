from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from tenant.models import Tenant

# from django.shortcuts import reverse
# from django.test import RequestFactory


User = get_user_model()


class SignalTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)

    def change_domain_urls_signal(self):
        # TODO
        pass

    def test_handle_tenant_site_domain_update__long_domain_truncates_site_name(self):
        """A tenant whose full domain exceeds Site.name's 50-char limit is still
        created successfully.

        The post_schema_sync handler sets the tenant's Site from its domain; it
        previously did Site.objects.update(name=domain, ...), which raised
        "value too long for type character varying(50)" for a long deck subdomain
        because Site.name is varchar(50). The name label is now truncated to fit,
        while Site.domain (varchar(100), used by allauth to build URLs) keeps the
        full value.
        """
        # A valid subdomain longer than Site.name's 50-char max, so the derived
        # "<name>.<ROOT_DOMAIN>" domain overflows Site.name without the fix.
        long_name = "a" * 55
        with schema_context(get_public_schema_name()):
            tenant = Tenant(schema_name="longsitename", name=long_name)
            tenant.save()

        with tenant_context(tenant):
            site = Site.objects.first()
            full_domain = tenant.get_primary_domain().domain
            name_max = Site._meta.get_field("name").max_length
            # domain (100) keeps the full value; name (50) is truncated to fit
            self.assertEqual(site.domain, full_domain)
            self.assertEqual(site.name, full_domain[:name_max])
            self.assertLessEqual(len(site.name), name_max)
