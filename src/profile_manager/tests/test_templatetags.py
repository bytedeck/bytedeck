from django.template import Context, Template

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

from profile_manager.templatetags.profile_tags import PEOPLE_LIST_DESCRIPTIONS, people_list_description


class PeopleListDescriptionTests(ByteDeckTenantTestCase):
    """Tests for the people_list_description tag, the hover text of the lists of people (#2136)."""

    def test_people_list_description__every_list_in_the_decks_own_words(self):
        """Each list is described with the deck's custom names for a student and a group."""
        config = SiteConfig.get()
        config.custom_name_for_student = 'Member'
        config.custom_name_for_group = 'Cohort'
        config.save()

        self.assertEqual(
            people_list_description('yours'),
            'Members registered in a course in an open semester, in a cohort you are assigned to as the teacher',
        )
        for name in PEOPLE_LIST_DESCRIPTIONS:
            with self.subTest(name):
                self.assertNotIn('{', people_list_description(name))
                self.assertNotIn('student', people_list_description(name).lower())

    def test_people_list_description__escapes_the_custom_names(self):
        """A custom name is typed in Site Configuration, so it is escaped where the tag renders it."""
        config = SiteConfig.get()
        config.custom_name_for_student = '"><b>Kid'
        config.save()

        rendered = Template("{% load profile_tags %}{% people_list_description 'all' %}").render(Context())

        self.assertNotIn('<b>', rendered)
        self.assertIn('&quot;&gt;&lt;b&gt;kids', rendered)
