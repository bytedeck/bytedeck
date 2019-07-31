from django.test import TestCase
from model_mommy import mommy

from announcements.models import Announcement


class AnnouncementTestModel(TestCase):
    def setUp(self):
        self.announcement = mommy.make(Announcement)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.announcement, Announcement)
        self.assertEqual(str(self.announcement), self.announcement.title)
