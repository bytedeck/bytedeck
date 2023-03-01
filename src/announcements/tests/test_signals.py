from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from django_celery_beat.models import PeriodicTask
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context
from model_bakery import baker

from announcements.models import Announcement

User = get_user_model()
PUBLIC_SCHEMA = get_public_schema_name()


class AnnouncementsSignalsTest(TenantTestCase):

    def setUp(self):
        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)

    def test_save_announcement_signal(self):
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
