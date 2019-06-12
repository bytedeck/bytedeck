from django.apps import AppConfig


class PrerequisitesConfig(AppConfig):
    name = 'prerequisites'
    verbose_name = 'prerequisites'

    def ready(self):
        import prerequisites.signals  # noqa
