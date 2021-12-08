# import json
from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        from notifications.tasks import create_email_notification_tasks
        create_email_notification_tasks()
