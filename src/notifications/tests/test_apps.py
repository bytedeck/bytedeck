import json
from django.apps import apps
from django_celery_beat.models import PeriodicTask
from tenant_schemas.test.cases import TenantTestCase


class NotificationConfigTest(TenantTestCase):
    """ Tests of methods within apps.py"""

    def setUp(self):
        self.app = apps.get_app_config('notifications')

    def test_ready_task_is_created(self):
        """ The email notifcation task should be created in ready() on whent he app starts up"""
        # DOES NOT HAPPEN ON TEST DB!
        # This is because the ready() method runs on the default db, before django knows it is testing.
        # https://code.djangoproject.com/ticket/22002
        tasks = PeriodicTask.objects.filter(task='notifications.tasks.email_notifications_to_users')
        self.assertEqual(tasks.count(), 0)

        # try running manually now that we're in testing:
        self.app.ready()
        tasks = PeriodicTask.objects.filter(task='notifications.tasks.email_notifications_to_users')
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks[0].headers, json.dumps({"_schema_name": "test"}))

        # ready is idempotent, doesn't cause problems running it again, doesn't create a new task:
        self.app.ready()
        tasks = PeriodicTask.objects.filter(task='notifications.tasks.email_notifications_to_users')
        self.assertEqual(tasks.count(), 1)

    def test_create_email_notification_tasks(self):
        """ A task should have been created for the test tenant"""
        self.app.create_email_notification_tasks()
        tasks = PeriodicTask.objects.filter(task='notifications.tasks.email_notifications_to_users')
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks[0].headers, json.dumps({"_schema_name": "test"}))
