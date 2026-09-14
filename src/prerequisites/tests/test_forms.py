import re

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.forms import PrereqFormInline
from prerequisites.models import Prereq

User = get_user_model()


class PrereqFormInlineMediaTest(ByteDeckTenantTestCase):
    """The checkbox-layout fix (issue #1978) is shipped as a static CSS file loaded through the
    form's own Media, so it arrives with {{ form.media.css }} rather than an inline <style>.
    """

    CSS = 'prerequisites/css/advanced_prereqs_form.css'

    def setUp(self):
        """Create a tenant client and a teacher user for the tests."""
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


class AdvancedPrereqsFormAddRowTest(ByteDeckTenantTestCase):
    """The advanced prereqs form has to be able to grow: "Add Another Prerequisite" appends a
    blank row to the formset, so a teacher is not limited to the single spare row the formset
    renders and can add several prerequisites in one visit (issue #2707).
    """

    def setUp(self):
        """Log in a teacher, the only role allowed to edit prerequisites."""
        self.teacher = baker.make(User, is_staff=True)
        self.client.force_login(self.teacher)

    def prereq_form_urls(self):
        """Return the prereq-update URLs of a new quest and a new badge. Both pages render
        advanced_prereqs_form.html, so every assertion here has to hold for both.
        """
        return (
            reverse('quests:quest_prereqs_update', args=[baker.make('quest_manager.Quest').pk]),
            reverse('badges:badge_prereqs_update', args=[baker.make('badges.Badge').pk]),
        )

    def test_advanced_prereqs_form_page__renders_the_add_another_prerequisite_button(self):
        """PrereqFormsetHelper renders the button itself, as one of its inputs, so it appears
        wherever the template pack puts Save and Cancel. Nothing outside the helper targets that
        markup, which is what lets the button's presence be asserted here rather than only in a
        browser.
        """
        for url in self.prereq_form_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                button = re.search(r'<input[^>]*id="add-form"[^>]*>', response.content.decode())
                self.assertIsNotNone(button, "no add-row button on the advanced prereqs form")
                # type=button, not submit: it grows the formset, it must not save it.
                self.assertIn('type="button"', button.group())
                self.assertIn('value="Add Another Prerequisite"', button.group())

    def test_advanced_prereqs_form_page__renders_the_hooks_the_add_row_script_needs(self):
        """Clicking the button clones the formset's hidden empty form into the table and bumps
        TOTAL_FORMS, so all three have to be on the page under the selectors the script uses.
        A missing one is invisible at runtime: the button is simply inert.
        """
        for url in self.prereq_form_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'id="id_prereq_formset"')
                self.assertContains(response, 'class="hidden empty-form"')
                self.assertContains(
                    response,
                    'id="id_prerequisites-prereq-parent_content_type-parent_object_id-TOTAL_FORMS"',
                )

    def test_advanced_prereqs_form_page__saves_a_prerequisite_added_beyond_the_rendered_rows(self):
        """The rows the button adds are ordinary extra forms, so posting more forms than the page
        rendered saves them. This is what a teacher gets after clicking the button: TOTAL_FORMS
        one higher than the formset started with, and a value in the new row.
        """
        quest = baker.make('quest_manager.Quest')
        prereq_quest = baker.make('quest_manager.Quest')
        url = reverse('quests:quest_prereqs_update', args=[quest.pk])
        prefix = 'prerequisites-prereq-parent_content_type-parent_object_id'
        content_type = ContentType.objects.get_for_model(prereq_quest)

        # Exactly what the browser posts after one click: the spare row the formset always
        # renders (extra=1) left untouched, and the row the button appended after it.
        empty_row = {f'{prefix}-0-prereq_count': 1, f'{prefix}-0-or_prereq_count': 1, f'{prefix}-0-id': ''}
        added_row = {
            f'{prefix}-1-prereq_object': f'{content_type.pk}-{prereq_quest.pk}',
            f'{prefix}-1-prereq_count': 1,
            f'{prefix}-1-or_prereq_count': 1,
            f'{prefix}-1-id': '',
        }
        response = self.client.post(url, {
            f'{prefix}-TOTAL_FORMS': 2,
            f'{prefix}-INITIAL_FORMS': 0,
            f'{prefix}-MIN_NUM_FORMS': 0,
            f'{prefix}-MAX_NUM_FORMS': 1000,
            **empty_row,
            **added_row,
        })

        self.assertRedirects(response, quest.get_absolute_url())
        self.assertQuerySetEqual(Prereq.objects.all_parent(quest), [prereq_quest], lambda p: p.prereq_object)
