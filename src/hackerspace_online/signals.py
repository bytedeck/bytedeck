from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django_tenants.utils import get_public_schema_name, tenant_context

from tenant.models import Tenant


def change_domain_urls(sender, *args, **kwargs):
    """ Called via post_save signal from Sites app so that when the domain of the site changes,
    The domain_url of tenants will be updated.

    This should probably be in the Tenant app?
    """
    if 'instance' in kwargs and 'created' in kwargs and not kwargs['created']:
        try:
            public_tenant = Tenant.objects.get(schema_name='public')
        except ObjectDoesNotExist:
            return

        with transaction.atomic():
            all_tenants = Tenant.objects.exclude(schema_name='public')
            for tenant in all_tenants:
                domain = tenant.domain_url.split(public_tenant.domain_url)[0]
                tenant.domain_url = '{}{}'.format(domain, kwargs['instance'].domain)
                tenant.save()
            public_tenant.domain_url = kwargs['instance'].domain
            public_tenant.save()


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
        Site.objects.update(name=domain, domain=domain)
