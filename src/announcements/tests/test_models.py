from model_bakery import baker

from announcements.models import Announcement
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class AnnouncementTestModel(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Create an announcement shared across the test methods."""
        cls.announcement = baker.make(Announcement)

    def test_creation__str_returns_title(self):
        """An announcement is created and its string representation is its title."""
        self.assertIsInstance(self.announcement, Announcement)
        self.assertEqual(str(self.announcement), self.announcement.title)

    def test_get_comments__returns_only_connected_comments(self):
        """Test that an announcement returns comments connected to it"""
        comment1 = baker.make("comments.Comment", target_object=self.announcement)
        comment2 = baker.make("comments.Comment", target_object=self.announcement)

        # These comments shouldn't be included in the return
        baker.make("comments.Comment", target_object=baker.make(Announcement))
        baker.make("comments.Comment")

        self.assertCountEqual(self.announcement.get_comments(), [comment1, comment2])
