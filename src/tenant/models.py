from django.db import models

from tenant_schemas.models import TenantMixin


class Tenant(TenantMixin):
    name = models.CharField(max_length=100)
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True
