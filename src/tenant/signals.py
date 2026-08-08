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
    """ Create one tenant domain; invalidate the schema's cached deck row """
    from .utils import invalidate_current_deck_cache

    # any Tenant save (admin edit, cached-field refresh, future Stripe sync) must
    # invalidate the cached row the status banner reads, so changes show promptly
    invalidate_current_deck_cache(instance.schema_name)

    # Already have a domain so no further action required
    if instance.domains.exists():
        return

    if instance.schema_name == get_public_schema_name():
        domain = settings.ROOT_DOMAIN

    else:
        domain = f'{instance.name.lower()}.{settings.ROOT_DOMAIN}'

    instance.domains.create(domain=domain, is_primary=True)
