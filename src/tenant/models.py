import re

from django.core.exceptions import ValidationError
from django.db import models

from tenant_schemas.models import TenantMixin


def check_tenant_name(name):
    if not re.match(re.compile(r'^([a-zA-Z][a-zA-Z0-9]*(\-?[a-zA-Z0-9]+)*){,62}$'), name):
        raise ValidationError("Invalid string used for the tenant name.")


class Tenant(TenantMixin):
    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    name = models.CharField(max_length=100, unique=True, validators=[check_tenant_name])
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return '%s - %s' % (self.schema_name, self.domain_url)
