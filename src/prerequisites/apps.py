from django.apps import AppConfig


class PrerequisitesConfig(AppConfig):
    name = 'prerequisites'
    verbose_name = 'Prerequisites'

    def ready(self):
        import prerequisites.signals  # noqa
