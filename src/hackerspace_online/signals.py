from django.contrib.sites.models import Site
from django_tenants.utils import get_public_schema_name, tenant_context


def handle_tenant_site_domain_update(tenant, **kwargs):
    """
    This is called whenever a new tenant is created.
    Each tenant must has their own `Site` under their own schema.

    By default, it will have the value of settings.ROOT_DOMAIN or `example.com`

    django-allauth makes use of the `Site.domain` in order to generate the correct URLs for emails
    and also for callback URLs when using SocialProviders.

    So, when a tenant is created, this updates the domain to be the same domain they use for accessing their deck

    `post_schema_sync` will get called after a schema gets created from the save method on the tenant class.
    https://django-tenants.readthedocs.io/en/latest/use.html#signals
    """

    if tenant.schema_name == get_public_schema_name():
        return

    # Update the first Site.domain since it will be used for OAuth
    # Doing it this way so that we don't trigger any `post_save` signals

    with tenant_context(tenant):
        domain = tenant.get_primary_domain().domain
        # Site.name is varchar(50) but Site.domain is varchar(100); a long deck
        # subdomain can exceed 50 chars, so cap the human-readable name to the
        # field's max_length. allauth builds URLs from Site.domain (not name), so
        # truncating the label is harmless. Without this, creating a deck with a
        # long name raised "value too long for type character varying(50)".
        name_max = Site._meta.get_field("name").max_length
        Site.objects.update(name=domain[:name_max], domain=domain)
