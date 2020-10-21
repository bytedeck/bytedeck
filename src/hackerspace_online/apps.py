from django.apps import AppConfig


class HackerspaceConfig(AppConfig):
    name = 'hackerspace_online'
    verbose_name = "HackerspaceOnline"

    def ready(self):

        from django.contrib.sites.models import Site
        from django.db.models.signals import post_save
        from hackerspace_online.signals import change_domain_urls
        import hackerspace_online.celerybeat_signals # noqa

        post_save.connect(change_domain_urls, sender=Site)
