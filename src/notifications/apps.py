# import json

import json
from django.apps import AppConfig
from django.utils import timezone

from tenant_schemas.utils import get_tenant_model


class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        self.create_email_notification_tasks()

    def create_email_notification_tasks(self):
        """Create a scheduled beat tasks for each tenant, so that emails are sent out.  The tasks themselves are
        saved on the public schema"""

        # https://docs.djangoproject.com/en/3.2/ref/applications/#django.apps.AppConfig.ready
        # Can't import models at the module level, so need to import in the method.
        from django_celery_beat.models import CrontabSchedule, PeriodicTask
        from tenant.utils import get_root_url
        minute = 0

        for tenant in get_tenant_model().objects.exclude(schema_name='public'):

            # Bump each one by 1 minute, to spread out the tasks.
            email_notifications_schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour='5',
                day_of_week='*',
                day_of_month='*',
                month_of_year='*',
                timezone=timezone.get_current_timezone()
            )

            minute += 1

            task_name = f'Send daily email of notifications for schema {tenant.schema_name}',
            # PeriodicTask doesn't have an update_or_create() method for some reason, so do it long way
            # https://github.com/celery/django-celery-beat/issues/106

            defaults = {
                'crontab': email_notifications_schedule,
                'task': 'notifications.tasks.email_notifications_to_users',
                'queue': 'default',
                'kwargs': json.dumps({  # beat needs json serializable args, so make sure they are
                    'root_url': get_root_url(),
                }),
                # Inject the schema name into the task's header, as that's where tenant-schema-celery
                # will be looking for it to ensure it is tenant aware
                'headers': json.dumps({
                    '_schema_name': tenant.schema_name,
                }),
                'one_off': True,
                'enabled': True,
            }

            try:
                task = PeriodicTask.objects.get(name=task_name)
                for key, value in defaults.items():
                    setattr(task, key, value)
                task.save()
            except PeriodicTask.DoesNotExist:
                new_values = {'name': task_name}
                new_values.update(defaults)
                task = PeriodicTask(**new_values)
                task.save()

            # End manual update_or_create() ############
