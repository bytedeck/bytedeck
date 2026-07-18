import os

from django.conf import settings

from tenant_schemas_celery.app import CeleryApp
from celery.schedules import crontab
from celery.signals import task_failure

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
        "options": {
            "queue": "default",
        }
    },
    "Invalidate Profile XP Cache for all schemas daily task": {
        "task": "profile_manager.tasks.invalidate_profile_xp_cache_in_all_schemas",
        "schedule": crontab(minute=0, hour=0),
        "options": {
            "queue": "default",
        }
    },
    "Delete Notifications older than 90 days for all schemas daily task": {
        "task": "notifications.tasks.delete_old_notifications_for_all_tenants",
        "schedule": crontab(minute=0, hour=1),
        "options": {
            "queue": "default",
        }
    },
    "Clear expired sessions in all schemas daily task": {
        "task": "tenant.tasks.clear_expired_sessions_in_all_schemas",
        "schedule": crontab(minute=0, hour=2),
        "options": {
            "queue": "default",
        }
    },
}


@task_failure.connect
def email_admins_on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    """Email ADMINS when any celery task raises during execution.

    Without this, task exceptions vanish into the worker log: no task in the
    project configures retries, there is no result backend, and
    CELERY_TASK_IGNORE_RESULT is on -- so a broken periodic task could fail
    silently for weeks. Throttled via the cache to one email per
    task+exception type per hour, so a failing per-schema fan-out can't send
    hundreds of emails. Never raises: error reporting must not be able to
    take down the worker.

    Arguments (all supplied by celery's task_failure signal):
        sender: the task object that failed (its `name` attribute is used;
            falls back to repr() if absent).
        task_id (str): id of the failed task instance.
        exception (Exception): the exception the task raised.
        einfo: billiard ExceptionInfo whose str() is the traceback.
        **kwargs: remaining signal arguments (args, kwargs, traceback);
            accepted and ignored, as the signal contract requires.

    Returns None.
    """
    from django.core.cache import cache
    from django.core.mail import mail_admins

    try:
        task_name = getattr(sender, 'name', None) or repr(sender)
        throttle_key = f'task-failure-emailed:{task_name}:{type(exception).__name__}'
        # cache.add is atomic: returns False if the key already exists.
        if not cache.add(throttle_key, True, timeout=60 * 60):
            return
        mail_admins(
            subject=f'Celery task failed: {task_name}',
            message=(
                f'Task: {task_name}\n'
                f'Task id: {task_id}\n'
                f'Exception: {exception!r}\n\n'
                f'{einfo}\n\n'
                'Further failures of this task with the same exception type are '
                'suppressed for 1 hour.'
            ),
            fail_silently=True,
        )
    except Exception:
        # e.g. the cache itself is down -- swallow it; the original task
        # failure is already in the worker log.
        pass


# @app.task(bind=True)
# def debug_task(self):
#     print('Request: {0!r}'.format(self.request))
