# import json
from django.apps import AppConfig
from django.db.utils import ProgrammingError


class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        # if the project is already up and running, all the tables should exist and this should run
        # otherwise, if this is being run for the first time (e.g. testing or new db), this with cause an exception
        try:
            from notifications.tasks import create_email_notification_tasks
            create_email_notification_tasks()
        except ProgrammingError:
            pass
