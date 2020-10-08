from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from announcements.models import Announcement


class AnnouncementTestModel(TenantTestCase):
    def setUp(self):
        self.announcement = baker.make(Announcement)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.announcement, Announcement)
        self.assertEqual(str(self.announcement), self.announcement.title)
