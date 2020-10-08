from django.apps import AppConfig


class TenantConfig(AppConfig):
    name = 'tenant'

    def ready(self):
        from django.db.models.signals import post_save
        from django_tenants.models import TenantMixin
        from django_tenants.signals import post_schema_sync

        from tenant.models import Tenant
        from tenant.signals import initialize_tenant_with_data, tenant_save_callback

        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
        post_save.connect(tenant_save_callback, sender=Tenant)
