from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from django_celery_beat.models import PeriodicTask

from model_mommy import mommy

from announcements.models import Announcement

User = get_user_model()


class AnnouncementsSignalsTest(TestCase):

    def setUp(self):
        self.teacher = mommy.make(User, username='teacher', is_staff=True)
        self.student = mommy.make(User, username='student', is_staff=False)

    def test_save_announcement_signal(self):
        """ test that after a model is saved that a celery-beat tasks exists to publish it if conditions are correct
        """
        announcement = mommy.make(Announcement)

        # by default announcements are drafts, so no periodic task for it should exist
        # announcement publishing tasks should have the ID in the name somewhere
        with self.assertRaises(ObjectDoesNotExist):
            PeriodicTask.objects.get(name__contains=announcement.id)

        # change the announcement to auto_publish, and the save signal creates a tasks to publish it
        announcement.auto_publish = True
        announcement.save()

        task = PeriodicTask.objects.get(name__contains=announcement.id)

        self.assertEqual(task.queue, "default")

        # task should have a schedule date matching the announcement:
        self.assertEqual(task.clocked.clocked_time, announcement.datetime_released)

        # changing the announcement to not be a draft should cause the signal to delete the task
        announcement.draft = False
        announcement.save()

        with self.assertRaises(ObjectDoesNotExist):
            PeriodicTask.objects.get(name__contains=announcement.id)
