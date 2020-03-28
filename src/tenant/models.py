from django.db import models

from tenant_schemas.models import TenantMixin


class Tenant(TenantMixin):
    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    name = models.CharField(max_length=100)
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)
