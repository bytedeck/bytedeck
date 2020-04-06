from django.apps import AppConfig


class HackerspaceConfig(AppConfig):
    name = 'hackerspace_online'
    verbose_name = "HackerspaceOnline"

    def ready(self):
        # self.register_config()

        from django.contrib.sites.models import Site
        from django.db.models.signals import post_save
        from hackerspace_online.signals import change_domain_ulrs

        post_save.connect(change_domain_ulrs, sender=Site)

    # def register_config(self):
    #     import djconfig
    #     from .forms import HackerspaceConfigForm

    #     djconfig.register(HackerspaceConfigForm)
