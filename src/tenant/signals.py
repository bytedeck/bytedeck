from django.conf import settings
from django.db import connection

from django_tenants.utils import get_public_schema_name

from .initialization import load_initial_tenant_data


def initialize_tenant_with_data(sender, tenant, **kwargs):
    connection.set_tenant(tenant)
    load_initial_tenant_data()


def tenant_save_callback(sender, instance, **kwargs):
    """ Create one tenant domain """

    # Already have a domain so no further action required
    if instance.domains.exists():
        return

    if instance.schema_name == get_public_schema_name():
        domain = settings.ROOT_DOMAIN

    else:
        domain = f'{instance.name.lower()}.{settings.ROOT_DOMAIN}'

    instance.domains.create(domain=domain, is_primary=True)
