from django.conf import settings
from django.utils.text import slugify

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


def deck_subdomain(schema_name):
    """Return the subdomain a new deck is served from, built from its schema name.

    A tenant's name is free text wherever a Tenant is made without `full_clean()` (initdb
    names the Library 'Shared Library'), and a name with a space or an accent gives a domain
    no browser can request (#2404). The schema name is the tenant's identity instead, but it
    is not a hostname either: `generate_schema_name()` turns a name's dashes into underscores,
    which a hostname cannot hold, and a schema made from free text keeps its spaces. So it is
    slugified and its underscores turned back into dashes. For every name `check_tenant_name`
    accepts, that is the name itself, the subdomain the deck-request form promises.

    Args:
        schema_name (str): the tenant's schema name.

    Returns:
        str: a lower-case subdomain made of letters, digits and dashes.
    """
    return slugify(schema_name).replace('_', '-')


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
        domain = f'{deck_subdomain(instance.schema_name)}.{settings.ROOT_DOMAIN}'

    instance.domains.create(domain=domain, is_primary=True)
