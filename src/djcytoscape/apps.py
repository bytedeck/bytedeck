from django.apps import AppConfig


class DjcytoscapeConfig(AppConfig):
    name = 'djcytoscape'
    verbose_name = "Quest Maps"

    def ready(self):
        # connect signals to app
        import djcytoscape.signals # noqa
