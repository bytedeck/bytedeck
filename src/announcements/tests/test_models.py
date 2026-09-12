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


class AnnouncementSearchTests(ByteDeckTenantTestCase):
    """`AnnouncementQuerySet.search` narrows a list to what the reader asked for (#2667)."""

    @classmethod
    def setUpTestData(cls):
        """Create announcements whose titles and content differ, so a match can be traced to one or the other."""
        cls.field_trip = baker.make(Announcement, title="Field trip on Friday", content="<p>Bring a bagged lunch.</p>")
        cls.lunch_menu = baker.make(Announcement, title="Cafeteria menu", content="<p>Lunch is pizza this week.</p>")
        cls.club_signup = baker.make(Announcement, title="Robotics club", content="<p>Sign up at the office.</p>")

    def test_search__matches_a_word_in_the_title(self):
        """A word in the title finds the announcement, and leaves the others out."""
        self.assertQuerySetEqual(Announcement.objects.all().search("robotics"), [self.club_signup])

    def test_search__matches_a_word_in_the_content(self):
        """A word only in the body finds the announcement: the body is most of what an announcement says."""
        self.assertQuerySetEqual(Announcement.objects.all().search("bagged"), [self.field_trip])

    def test_search__is_case_insensitive_and_matches_part_of_a_word(self):
        """Searching is by substring, ignoring case, so a half-remembered word still finds it."""
        self.assertQuerySetEqual(Announcement.objects.all().search("ROBOT"), [self.club_signup])

    def test_search__every_word_has_to_match_something(self):
        """Several words narrow rather than widen: each has to match, though not all the same field."""
        # "lunch" is in one title's content and the other's title; "friday" only in the field trip's title
        self.assertQuerySetEqual(Announcement.objects.all().search("lunch friday"), [self.field_trip])
        self.assertQuerySetEqual(Announcement.objects.all().search("lunch pizza"), [self.lunch_menu])

    def test_search__no_match_returns_nothing(self):
        """A term matching nothing returns an empty list rather than everything."""
        self.assertQuerySetEqual(Announcement.objects.all().search("kayaking"), [])

    def test_search__an_empty_term_leaves_the_list_alone(self):
        """No search term means no filtering, so an unsearched page still shows everything."""
        self.assertQuerySetEqual(
            Announcement.objects.all().search("").order_by('pk'),
            [self.field_trip, self.lunch_menu, self.club_signup],
        )
