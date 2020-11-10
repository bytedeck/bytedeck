from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from django_celery_beat.models import PeriodicTask
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.utils import get_public_schema_name, schema_context

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

        self.assertEqual(task.clocked.clocked_time, announcement.datetime_released)

        # changing the announcement to not be a draft should cause the signal to delete the task
        announcement.draft = False
        announcement.save()

        with self.assertRaises(ObjectDoesNotExist):
            PeriodicTask.objects.get(name__contains=announcement.id)

        with schema_context(PUBLIC_SCHEMA):
            with self.assertRaises(ObjectDoesNotExist):
                PeriodicTask.objects.get(name__contains=announcement.id)
