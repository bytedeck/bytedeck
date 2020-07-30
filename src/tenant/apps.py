from django.apps import AppConfig


class TenantConfig(AppConfig):
    name = 'tenant'

    def ready(self):
        from tenant_schemas.models import TenantMixin
        from tenant_schemas.signals import post_schema_sync
        from tenant.signals import initialize_tenant_with_data

        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
