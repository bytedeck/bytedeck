from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.utils import timezone

from django_celery_beat.models import PeriodicTask, PeriodicTasks
from django_tenants.utils import get_public_schema_name, schema_context
from model_bakery import baker

from announcements.models import Announcement
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()
PUBLIC_SCHEMA = get_public_schema_name()


class AnnouncementsSignalsTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and student shared across the test methods."""
        cls.teacher = baker.make(User, username='teacher', is_staff=True)
        cls.student = baker.make(User, username='student', is_staff=False)

    def test_save_announcement_signal__creates_and_deletes_publish_task(self):
        """
        Test that after a model is saved that a celery-beat tasks exists to publish it if conditions are correct.
        The task should also exists in the public schema.
        """

        announcement = baker.make(Announcement)
        # save_announcement_signal() method called via `@receiver(post_save, sender=Announcement)`

        # by default announcements are drafts, so no periodic task for it should exist
        # announcement publishing tasks should have the ID in the name somewhere
        with self.assertRaises(ObjectDoesNotExist):
            PeriodicTask.objects.get(name__contains=announcement.id)

        # change the announcement to auto_publish, and the save signal creates a tasks to publish it
        announcement.auto_publish = True
        announcement.save()

        task = PeriodicTask.objects.get(name__contains=announcement.id)

        self.assertEqual(task.queue, 'default')

        public_task = None
        with schema_context(PUBLIC_SCHEMA):
            public_task = PeriodicTask.objects.get(name__contains=announcement.id)

        self.assertIsNotNone(public_task)
        self.assertEqual(task.name, public_task.name)
        self.assertEqual(task.queue, public_task.queue)

        # TODO: Uncomment again when we are using ClockedSchedule and not CrontabSchedule
        # self.assertEqual(task.clocked.clocked_time, announcement.datetime_released)

        # task should have a schedule date matching the announcement:
        self.assertEqual(int(task.crontab.hour), announcement.datetime_released.hour)
        self.assertEqual(int(task.crontab.minute), announcement.datetime_released.minute)
        self.assertEqual(int(task.crontab.day_of_month), announcement.datetime_released.day)
        self.assertEqual(int(task.crontab.month_of_year), announcement.datetime_released.month)

        # changing the announcement to not be a draft should cause the signal to delete the task
        announcement.draft = False
        announcement.save()

        with self.assertRaises(ObjectDoesNotExist):
            PeriodicTask.objects.get(name__contains=announcement.id)

        with schema_context(PUBLIC_SCHEMA):
            with self.assertRaises(ObjectDoesNotExist):
                PeriodicTask.objects.get(name__contains=announcement.id)

    def test_save_announcement_signal__when_PeriodicTask_exists(self):
        """
        Test that after an announcement is saved, if the PeriodicTask already exists, the method doesn't crash and the
        PeriodicTask is re-used instead.

        This is because there PeriodicTask doesn't have an update_or_create() method for some reason, so we need to use get
        and catch the exception https://github.com/celery/django-celery-beat/issues/106
        """
        announcement = baker.make(Announcement, auto_publish=True)
        # Task should exist (created by signal)
        task = PeriodicTask.objects.get(name__contains=announcement.id)

        # change the announcement and resave to force recall of `save_announcement_signal()`
        announcement.title = "New Title"
        announcement.save()
        task2 = PeriodicTask.objects.get(name__contains=announcement.id)
        # Didn't create a new PeriodicTask object
        self.assertEqual(task, task2)

    def test_save_announcement_signal__moving_onto_a_used_minute_tells_beat(self):
        """Moving a scheduled announcement onto a minute another announcement already uses reschedules its publish task,
        and records the change where beat looks for it.

        The minute's schedule already exists, so nothing new is created that would record a change on its own. Without
        the record, beat keeps the task at its old time and publishes the announcement early (#820).
        """
        release = timezone.now() + timedelta(days=1)
        moved = baker.make(Announcement, auto_publish=True, datetime_released=release)
        baker.make(Announcement, auto_publish=True, datetime_released=release + timedelta(minutes=5))

        with schema_context(PUBLIC_SCHEMA):
            last_change_before = PeriodicTasks.last_change()

        moved.datetime_released = release + timedelta(minutes=5)
        moved.save()

        task_name = f"Autopublish task for Announcement #{moved.id} on schema {connection.schema_name}"
        with schema_context(PUBLIC_SCHEMA):
            public_task = PeriodicTask.objects.get(name=task_name)
            self.assertEqual(int(public_task.crontab.minute), moved.datetime_released.minute)
            self.assertGreater(PeriodicTasks.last_change(), last_change_before)
