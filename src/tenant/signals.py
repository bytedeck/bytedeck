from django.db import connection

from siteconfig.models import SiteConfig

from .initialization import load_initial_tenant_data


def initialize_tenant_with_data(sender, tenant, **kwargs):
    connection.set_tenant(tenant)

    if not SiteConfig.objects.exists():
        load_initial_tenant_data()
