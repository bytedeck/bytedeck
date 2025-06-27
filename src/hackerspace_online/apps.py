from django.apps import AppConfig


class HackerspaceConfig(AppConfig):
    name = 'hackerspace_online'
    verbose_name = "HackerspaceOnline"

    def ready(self):

        from django.contrib.sites.models import Site
        from django.db.models.signals import post_save
        from django_tenants.models import TenantMixin, post_schema_sync
        from hackerspace_online.signals import change_domain_urls, handle_tenant_site_domain_update
        import hackerspace_online.celerybeat_signals # noqa
        from django.conf import settings
        import stripe

        post_save.connect(change_domain_urls, sender=Site)
        post_schema_sync.connect(handle_tenant_site_domain_update, sender=TenantMixin)

        if settings.STRIPE_LIVE_MODE:
            stripe.api_key = settings.STRIPE_LIVE_SECRET_KEY
        else:
            stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
