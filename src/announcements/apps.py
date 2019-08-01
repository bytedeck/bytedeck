from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    name = 'announcements'
    verbose_name = 'Announcements'

    def ready(self):
        import announcements.signals  # noqa
