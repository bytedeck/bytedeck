from model_mommy import mommy
from tenant_schemas.test.cases import TenantTestCase

from announcements.models import Announcement


class AnnouncementTestModel(TenantTestCase):
    def setUp(self):
        self.announcement = mommy.make(Announcement)

    def test_badge_type_creation(self):
        self.assertIsInstance(self.announcement, Announcement)
        self.assertEqual(str(self.announcement), self.announcement.title)
