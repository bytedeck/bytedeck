from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

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
