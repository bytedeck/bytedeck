from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.forms import PrereqFormInline

User = get_user_model()


class PrereqFormInlineMediaTest(ByteDeckTenantTestCase):
    """The checkbox-layout fix (issue #1978) is shipped as a static CSS file loaded through the
    form's own Media, so it arrives with {{ form.media.css }} rather than an inline <style>.
    """

    CSS = 'prerequisites/css/advanced_prereqs_form.css'

    def setUp(self):
        """Create a tenant client and a teacher user for the tests."""
        self.client = TenantClient(self.tenant)
        self.teacher = baker.make(User, is_staff=True)

    def test_media__includes_prereq_css(self):
        """PrereqFormInline declares the layout-fix stylesheet in its Media."""
        self.assertIn(self.CSS, str(PrereqFormInline().media))

    def test_advanced_prereqs_form_page__loads_the_css(self):
        """The stylesheet is actually emitted on the advanced prereqs form page — for both the
        quest and badge prereq forms, which share advanced_prereqs_form.html.
        """
        self.client.force_login(self.teacher)
        quest = baker.make('quest_manager.Quest')
        badge = baker.make('badges.Badge')

        for url in (reverse('quests:quest_prereqs_update', args=[quest.pk]),
                    reverse('badges:badge_prereqs_update', args=[badge.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.CSS)
