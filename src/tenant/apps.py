from django.apps import AppConfig


class TenantConfig(AppConfig):
    name = 'tenant'

    def ready(self):
        from django_tenants.models import TenantMixin
        from django_tenants.signals import post_schema_sync
        from tenant.signals import create_superuser

        post_schema_sync.connect(create_superuser, sender=TenantMixin)
