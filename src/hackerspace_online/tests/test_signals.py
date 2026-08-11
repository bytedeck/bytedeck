from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from hackerspace_online.signals import change_domain_urls
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.models import Tenant

# from django.shortcuts import reverse
# from django.test import RequestFactory


User = get_user_model()


class SignalTest(ByteDeckTenantTestCase):
    """Tests the signal handlers that keep the Site record in sync with tenant domain changes."""

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
            tenant.full_clean()
            tenant.save()

        with tenant_context(tenant):
            site = Site.objects.first()
            full_domain = tenant.get_primary_domain().domain
            name_max = Site._meta.get_field("name").max_length
            # domain (100) keeps the full value; name (50) is truncated to fit
            self.assertEqual(site.domain, full_domain)
            self.assertEqual(site.name, full_domain[:name_max])
            self.assertLessEqual(len(site.name), name_max)

    def test_change_domain_urls__is_a_noop_on_create(self):
        """change_domain_urls only acts on Site updates; a create (created=True) returns
        immediately, before even looking up the public tenant."""
        with schema_context(get_public_schema_name()):
            site = Site.objects.first()
            with patch.object(Tenant.objects, 'get') as mock_get:
                self.assertIsNone(change_domain_urls(sender=Site, instance=site, created=True))
            # The guard returns before the tenant lookup, so get() is never reached.
            mock_get.assert_not_called()

    def test_change_domain_urls__returns_when_public_tenant_missing(self):
        """If the public tenant lookup fails, the handler returns quietly rather than raising."""
        with schema_context(get_public_schema_name()):
            site = Site.objects.first()
            with patch.object(Tenant.objects, 'get', side_effect=Tenant.DoesNotExist):
                self.assertIsNone(change_domain_urls(sender=Site, instance=site, created=False))
