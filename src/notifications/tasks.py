from __future__ import absolute_import, unicode_literals
import json

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django.utils import timezone
from tenant_schemas.utils import get_tenant_model

from hackerspace_online.celery import app
# from celery import shared_task

from siteconfig.models import SiteConfig

from .models import Notification

User = get_user_model()


@app.task(name='notifications.tasks.email_notifications_to_users')
def email_notifications_to_users(root_url):

    notification_emails = get_notification_emails(root_url)
    connection = mail.get_connection()
    connection.send_messages(notification_emails)
    # send_email_notification_tenant.delay(root_url)


def get_notification_emails(root_url):
    users_to_email = User.objects.filter(profile__get_notifications_by_email=True)
    subject = '{} Notifications'.format(SiteConfig.get().site_name_short)
    html_template = get_template('notifications/email_notifications.html')

    notification_emails = []

    for user in users_to_email:

        to_email_address = user.email
        unread_notifications = Notification.objects.all_unread(user)

        if unread_notifications:
            text_content = str(unread_notifications)
            
            html_content = html_template.render({
                'user': user,
                'notifications': unread_notifications,
                'root_url': root_url,
                'profile_edit_url': reverse('profiles:profile_edit_own')
            })
            email_msg = EmailMultiAlternatives(subject, text_content, to=[to_email_address])
            email_msg.attach_alternative(html_content, "text/html")
            notification_emails.append(email_msg)

    return notification_emails


def create_email_notification_tasks():
    """Create a scheduled beat tasks for each tenant, so that emails are sent out.  The tasks themselves are
    saved on the public schema
    
    THIS METHOD MUST REMAIN IDEMPOTENT, so that it can be run multiple times without errors
    """

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
