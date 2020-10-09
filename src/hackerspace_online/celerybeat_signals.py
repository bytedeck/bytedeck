"""
As of this date (October 2020), `tenant-schemas-celery` does not work out of the box with django-celery-beat's` PeriodicTask`.
django_celery_beat.schedulers.DatabaseScheduler only monitors changes and executes tasks that are inside the `public` schema.

What this currently does is that any PeriodicTask created in a tenant schema will also be created in the public schema.
`tenant-schemas-celery` takes care of executing the task in the proper schema as long as the `headers` contain the `_schema_name`.

For more details on why this exists, see https://github.com/bernardopires/django-tenant-schemas/issues/526#issuecomment-388101839
"""
from django.db import connection
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.forms import model_to_dict

from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
from django_tenants.utils import get_public_schema_name, schema_context

PUBLIC_SCHEMA = get_public_schema_name()


@receiver(pre_save, sender=ClockedSchedule)
@receiver(pre_save, sender=CrontabSchedule)
@receiver(pre_save, sender=SolarSchedule)
@receiver(pre_save, sender=IntervalSchedule)
def save_schedule_to_public_schema(sender, instance, **kwargs):

    if connection.schema_name == PUBLIC_SCHEMA:
        return

    instance_dict = model_to_dict(instance)
    instance_dict.pop('id')

    with schema_context(PUBLIC_SCHEMA):
        sender.objects.get_or_create(**instance_dict)


@receiver(pre_save, sender=PeriodicTask)
def save_task_to_public_schema(sender, instance, **kwargs):

    if connection.schema_name == PUBLIC_SCHEMA:
        return

    task_dict = model_to_dict(instance)
    task_name = task_dict.pop('name')

    # Remove id since it will be a different id in the public schema
    del task_dict['id']

    schedules_map = {
        'clocked': ClockedSchedule,
        'interval': IntervalSchedule,
        'crontab': CrontabSchedule,
        'solar': SolarSchedule
    }

    # Since a `clocked`, `interval`, `crontab`, or `solar` schedule are created in the current schema
    # We would want to change the `id` used by the `PeriodicTask` object.
    # e.g. A ClockedSchedule object's id saved with this task is 4 but it can be different when it was saved
    # to the public schema.
    for schedule_type, schedule_model in schedules_map.items():
        if task_dict[schedule_type] is not None:
            # Fetch the schedule from the current schema and get the details
            schedule_id = task_dict[schedule_type]
            schedule_dict = model_to_dict(schedule_model.objects.get(pk=schedule_id))

            del schedule_dict['id']

            # Fetch the schedule created via `save_task_to_public_schema` receiver in the public schema
            with schema_context(PUBLIC_SCHEMA):
                public_schedule_obj = schedule_model.objects.get(**schedule_dict)

            # Replace the task schedule instance with a public schedule instance so that a public PeriodTask instance
            # uses a public schedule instance
            task_dict[schedule_type] = public_schedule_obj
            break

    with schema_context(PUBLIC_SCHEMA):
        task_qs = PeriodicTask.objects.filter(name=task_name)
        # Using `update` and `create` here since it doesn't call `.save()` method.
        # `.save()` method triggers signals and if used here, it would create a maximum recursion depth.
        if task_qs:
            task_qs.update(**task_dict)
        else:
            new_values = {'name': task_name}
            new_values.update(task_dict)
            PeriodicTask.objects.create(**new_values)


@receiver(pre_delete, sender=PeriodicTask)
def delete_task_in_public_schema(sender, instance, **kwargs):

    if connection.schema_name == PUBLIC_SCHEMA:
        return

    with schema_context(PUBLIC_SCHEMA):
        PeriodicTask.objects.filter(name=instance.name).delete()
