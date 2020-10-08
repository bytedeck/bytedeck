# import json

from django.apps import AppConfig

# from django.utils import timezone


# from django_celery_beat.models import CrontabSchedule, PeriodicTask
# from django_tenants.utils import get_tenant_model, tenant_context


class NotificationsConfig(AppConfig):
    name = 'notifications'

    # def ready(self):

    #     email_notifications_schedule, _ = CrontabSchedule.objects.get_or_create(
    #         minute='0',
    #         hour='5',
    #         timezone=timezone.get_current_timezone()
    #     )

    #     for tenant in get_tenant_model().objects.exclude(schema_name='public'):
    #         with tenant_context(tenant):

    #             PeriodicTask.objects.get_or_create(
    #                 crontab=email_notifications_schedule,
    #                 name='Send daily email notifications',
    #                 task='notifications.tasks.email_notifications_to_users',
    #                 queue='default',
    #                 kwargs=json.dumps({  # beat needs json serializable args, so make sure they are
    #                     'root_url': get_root_url(),
    #                 }),
    #                 headers=json.dumps({
    #                     '_schema_name': tenant.schema_name
    #                 }),
    #             )
