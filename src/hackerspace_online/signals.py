from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from tenant.models import Tenant


def change_domain_ulrs(sender, *args, **kwargs):
    if 'instance' in kwargs and 'created' in kwargs and not kwargs['created']:
        try:
            public_tenant = Tenant.objects.get(schema_name='public')
        except ObjectDoesNotExist:
            return

        with transaction.atomic():
            all_tenants = Tenant.objects.exclude(schema_name='public')
            for tenant in all_tenants:
                domain = tenant.domain_url.split(public_tenant.domain_url)[0]
                tenant.domain_url = '%s%s' % (domain, kwargs['instance'].domain)
                tenant.save()
            public_tenant.domain_url = kwargs['instance'].domain
            public_tenant.save()
