from django.db import models

from tenant_schemas.models import TenantMixin
from tenant_schemas.postgresql_backend.base import _check_schema_name


class Tenant(TenantMixin):
    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    domain_url = models.CharField(max_length=128, unique=True, editable=False)
    schema_name = models.CharField(max_length=63, unique=True, validators=[_check_schema_name], editable=False)
    name = models.CharField(max_length=100, unique=True, validators=[_check_schema_name])
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return '%s - %s' % (self.schema_name, self.domain_url)
