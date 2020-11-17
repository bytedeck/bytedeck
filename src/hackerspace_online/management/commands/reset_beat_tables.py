from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from tenant.models import Tenant


class Command(BaseCommand):

    help = 'Reset django_celery_beat tables to fix migration anomalies.'

    def handle(self, *args, **options):

        # Trick django into thinking that all tables are gone.
        # This is important so we can call migrate_schemas later.
        call_command('migrate_schemas', '--fake', 'django_celery_beat', 'zero')

        tenants = Tenant.objects.all()

        with connection.cursor() as cursor:
            for tenant in tenants:
                cursor.execute("""
                    DROP TABLE IF EXISTS {schema_name}.django_celery_beat_periodictask,
                               {schema_name}.{app_name}_periodictasks,
                               {schema_name}.{app_name}_solarschedule,
                               {schema_name}.{app_name}_clockedschedule,
                               {schema_name}.{app_name}_crontabschedule,
                               {schema_name}.{app_name}_intervalschedule
                    """.format(schema_name=tenant.schema_name, app_name='django_celery_beat'))

        call_command('migrate_schemas', 'django_celery_beat')
