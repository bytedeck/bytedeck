import json

from django.db import connection
from django.forms import model_to_dict
from django.utils import timezone

from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context

PUBLIC_SCHEMA = get_public_schema_name()


class PeriodicTaskSignalsTest(TenantTestCase):

    def test_save_CronSchedule_signal(self):
        """ Saving a CronSchedule model should also save it in the public schema """

        cron_schedule = CrontabSchedule(minute=5, hour=23, day_of_month=26, month_of_year=11)
        cron_schedule.save()
        cron_schedule_dict = model_to_dict(cron_schedule)
        del cron_schedule_dict['id']

        public_cron_schedule = None

        with schema_context(PUBLIC_SCHEMA):
            public_cron_schedule = CrontabSchedule.objects.get(**cron_schedule_dict)

        self.assertIsNotNone(public_cron_schedule)
        cron_schedule.refresh_from_db()
        self.assertEqual(cron_schedule.minute, public_cron_schedule.minute)
        self.assertEqual(cron_schedule.hour, public_cron_schedule.hour)
        self.assertEqual(cron_schedule.day_of_month, public_cron_schedule.day_of_month)
        self.assertEqual(cron_schedule.month_of_year, public_cron_schedule.month_of_year)

    def test_save_ClockedSchedule_signal(self):
        """ Saving a ClockedSchedule model should also save it in the public schema """

        now = timezone.now()
        clocked_schedule = ClockedSchedule(clocked_time=now)
        clocked_schedule.save()

        public_clocked_schedule = None

        with schema_context(PUBLIC_SCHEMA):
            public_clocked_schedule = ClockedSchedule.objects.get(clocked_time=now)

        self.assertIsNotNone(public_clocked_schedule)
        clocked_schedule.refresh_from_db()
        self.assertEqual(clocked_schedule.clocked_time, public_clocked_schedule.clocked_time)

    def test_save_IntervalSchedule_signal(self):
        """ Saving an IntervalSchedule model should also save it in the public schema """

        interval_schedule = IntervalSchedule(every=5, period=IntervalSchedule.DAYS)
        interval_schedule.save()

        public_interval_schedule = None

        with schema_context(PUBLIC_SCHEMA):
            public_interval_schedule = IntervalSchedule.objects.get(every=5, period=IntervalSchedule.DAYS)

        self.assertIsNotNone(public_interval_schedule)
        interval_schedule.refresh_from_db()
        self.assertEqual(interval_schedule.every, public_interval_schedule.every)
        self.assertEqual(interval_schedule.period, public_interval_schedule.period)
        self.assertEqual(str(interval_schedule), str(public_interval_schedule))

    def test_save_SolarSchedule_signal(self):
        """ Saving a SolarSchedule model should also save it in the public schema """

        params = dict(
            event='sunrise',
            latitude=37.281248,
            longitude=-122.000218
        )
        solar_schedule = SolarSchedule(**params)
        solar_schedule.save()

        public_solar_schedule = None

        with schema_context(PUBLIC_SCHEMA):
            public_solar_schedule = SolarSchedule.objects.get(**params)

        self.assertIsNotNone(public_solar_schedule)
        solar_schedule.refresh_from_db()
        self.assertEqual(solar_schedule.event, public_solar_schedule.event)
        self.assertEqual(solar_schedule.latitude, public_solar_schedule.latitude)
        self.assertEqual(solar_schedule.longitude, public_solar_schedule.longitude)

    def test_save_PeriodicTask_signal(self):
        """ Saving a periodic task should also save it in the public schema """

        schedule = CrontabSchedule(minute='5')
        schedule.save()

        defaults = {
            'name': 'Sample Task',
            'crontab': schedule,
            'task': 'just_a_random.task.run',
            'queue': 'default',
            'headers': json.dumps({
                '_schema_name': connection.schema_name,
            }),
            'one_off': True,
            'enabled': True,
        }

        task = PeriodicTask(**defaults)
        task.save()

        public_task = None

        with schema_context(PUBLIC_SCHEMA):
            public_task = PeriodicTask.objects.get(name=task.name)

        self.assertIsNotNone(public_task)
        self.assertEqual(task.name, public_task.name)
