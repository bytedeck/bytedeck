from django.conf import settings

from django_tenants.utils import get_public_schema_name, tenant_context

from .initialization import load_initial_tenant_data


def initialize_tenant_with_data(sender, tenant, **kwargs):
    """Seed a newly created tenant's schema with its initial data.

    Runs the initialization inside the new tenant's schema via ``tenant_context``
    so that the schema active before this handler ran is restored afterwards.

    The previous version called ``connection.set_tenant(tenant)`` and never
    switched back, leaving the connection pointed at the new tenant for the rest
    of the request. Because deck creation is served from the public schema, the
    later session write in ``SessionMiddleware`` then hit the *new* tenant's
    empty ``django_session`` table, which Django reads as the session having been
    deleted mid-request and raises ``SessionInterrupted``.
    """
    with tenant_context(tenant):
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
