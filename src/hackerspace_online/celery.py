import os

from django.conf import settings

from tenant_schemas_celery.app import CeleryApp
from celery.schedules import crontab

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hackerspace_online.settings')

app = CeleryApp('hackerspace_online')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


# This is the default schedule for celery beat
# We can add more schedules here or by using the admin interface
# See https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html
#
# If we need to remove a schedule, we can do so by using the admin interface
# We just need to ensure that it is not listed in the database since it will
# always attempt to run a schedule that is listed in the database even if
# it is not listed here or the name of the task is changed.
app.conf.beat_schedule = {
    "Send daily email of notifications to all schemas": {
        "task": "notifications.tasks.email_notification_to_users_on_all_schemas",
        "schedule": crontab(minute=0, hour=5),
    },
    "Invalidate Profile XP Cache for all schemas daily task": {
        "task": "profile_manager.tasks.invalidate_profile_xp_cache_in_all_schemas",
        "schedule": crontab(minute=0, hour=0),
    },
}


# @app.task(bind=True)
# def debug_task(self):
#     print('Request: {0!r}'.format(self.request))
