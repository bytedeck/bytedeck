from django.apps import AppConfig

class HackerspaceConfig(AppConfig):

    name = 'hackerspace_online'
    verbose_name = "HackerspaceOnline"

    def ready(self):
        self.register_config()
        # ...

    def register_config(self):
        import djconfig
        from .forms import HackerspaceConfigForm

        djconfig.register(HackerspaceConfigForm)
