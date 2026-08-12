from django.apps import AppConfig


class HackerspaceConfig(AppConfig):
    name = 'hackerspace_online'
    verbose_name = "HackerspaceOnline"

    def ready(self):

        from django_tenants.models import TenantMixin, post_schema_sync
        from hackerspace_online.signals import handle_tenant_site_domain_update
        import hackerspace_online.celerybeat_signals # noqa

        post_schema_sync.connect(handle_tenant_site_domain_update, sender=TenantMixin)
