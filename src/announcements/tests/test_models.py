from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase

from announcements.models import Announcement


class AnnouncementTestModel(TenantTestCase):
    def setUp(self):
        self.announcement = baker.make(Announcement)

    def test_creation(self):
        self.assertIsInstance(self.announcement, Announcement)
        self.assertEqual(str(self.announcement), self.announcement.title)

    def test_get_comments(self):
        """Test that an announcement returns comments connected to it"""
        comment1 = baker.make("comments.Comment", target_object=self.announcement)
        comment2 = baker.make("comments.Comment", target_object=self.announcement)

        # These comments shouldn't be included in the return
        baker.make("comments.Comment", target_object=baker.make(Announcement))
        baker.make("comments.Comment")

        self.assertCountEqual(self.announcement.get_comments(), [comment1, comment2])
