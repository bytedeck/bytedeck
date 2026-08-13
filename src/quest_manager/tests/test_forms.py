from django.contrib.auth import get_user_model
from django.utils import timezone

from crispy_forms.utils import render_crispy_form

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from quest_manager.forms import (
    TA_RESTRICTED_QUEST_FIELDS,
    QuestForm,
    SubmissionQuickReplyForm,
    SubmissionQuickReplyFormStudent,
    SubmissionReplyForm,
    TAQuestForm,
)
from quest_manager.models import Quest

User = get_user_model()


class QuestFormTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Provide a minimal set of valid QuestForm data shared across tests."""
        cls.minimal_valid_data = {
            "name": "Test Quest",
            "xp": 0,
            "max_repeats": 0,
            "max_xp": -1,
            "hours_between_repeats": 0,
            "sort_order": 0,
            "date_available": str(timezone.now().date()),
            "time_available": "0:00:00",
            "tags": "",
        }

    def test_QuestForm__minimal_valid_data_is_valid(self):
        """The minimal_valid_data provided in the setup method should be valid!"""
        form = QuestForm(data=self.minimal_valid_data)
        self.assertTrue(form.is_valid())

    def test_QuestForm__saves_quick_reply(self):
        """QuestForm exposes the quest-specific quick_reply field and saves it on the quest (#161)."""
        form_data = dict(self.minimal_valid_data)
        form_data["quick_reply"] = "See the rubric — you're missing the reflection paragraph."
        form = QuestForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        quest = form.save()
        self.assertEqual(quest.quick_reply, "See the rubric — you're missing the reflection paragraph.")

    def test_QuestForm__quick_reply_is_optional(self):
        """quick_reply is optional — a quest without it is still valid and defaults to empty (#161)."""
        form = QuestForm(data=self.minimal_valid_data)
        self.assertTrue(form.is_valid(), form.errors)
        quest = form.save()
        self.assertEqual(quest.quick_reply, "")

    def test_QuestForm__hideable_and_blocking_both_true_is_invalid(self):
        """If a quest is Blocking then it should not validate if it is also Hideable"""
        form_data = self.minimal_valid_data

        form_data["hideable"] = True
        form_data["blocking"] = True

        form = QuestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("Blocking quests cannot be Hideable.", form.errors['__all__'][0])

    def test_QuestForm__repeat_per_semester_with_unlimited_repeats_is_invalid(self):
        """A quest with unlimited repeats (max_repeats=-1) should not validate if it
        also has repeat_per_semester: unlimited repeats never run out, so there is
        nothing for a new semester to reset, and the combination previously caused
        404 errors for returning students (issue #1531).
        """
        form_data = self.minimal_valid_data

        form_data["max_repeats"] = -1
        form_data["repeat_per_semester"] = True

        form = QuestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("unlimited repeats", form.errors['__all__'][0])

    def test_QuestForm__repeat_per_semester_with_limited_repeats_is_valid(self):
        """A quest with a limited number of repeats can use repeat_per_semester."""
        form_data = self.minimal_valid_data

        form_data["max_repeats"] = 2
        form_data["repeat_per_semester"] = True

        form = QuestForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_QuestForm__unlimited_repeats_without_repeat_per_semester_is_valid(self):
        """A quest with unlimited repeats is valid as long as repeat_per_semester is off."""
        form_data = self.minimal_valid_data

        form_data["max_repeats"] = -1

        form = QuestForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_QuestForm__still_binds_the_TA_restricted_fields(self):
        """A teacher's quest form keeps the fields TAQuestForm drops: restricting a TA
        must not take those settings away from the teachers who are meant to have them."""
        form = QuestForm()
        for field_name in TA_RESTRICTED_QUEST_FIELDS:
            with self.subTest(field=field_name):
                self.assertIn(field_name, form.fields)


class TAQuestFormTest(ByteDeckTenantTestCase):
    """A student TA's quest form must not carry the fields only a teacher may set (#2384)."""

    @classmethod
    def setUpTestData(cls):
        """Provide minimal valid quest form data and the users a TA form needs."""
        cls.minimal_valid_data = {
            "name": "Test Quest",
            "xp": 0,
            "max_repeats": 0,
            "max_xp": -1,
            "hours_between_repeats": 0,
            "sort_order": 0,
            "date_available": str(timezone.now().date()),
            "time_available": "0:00:00",
            "tags": "",
        }
        cls.teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.ta = User.objects.create_user('test_ta')
        cls.ta.profile.is_TA = True
        cls.ta.profile.save()

    def test_TAQuestForm__does_not_bind_the_restricted_fields(self):
        """The restricted fields are absent from the form, not merely hidden: a hidden widget
        still binds whatever is posted, so hiding them only removed the control from the page."""
        form = TAQuestForm()
        rendered = str(form)
        for field_name in TA_RESTRICTED_QUEST_FIELDS:
            with self.subTest(field=field_name):
                self.assertNotIn(field_name, form.fields)
                self.assertNotIn(f'name="{field_name}"', rendered)

    def test_TAQuestForm__crispy_layout_drops_the_restricted_fields_and_keeps_the_rest(self):
        """The form renders through its crispy layout, which QuestForm builds naming fields this
        form no longer has. Those are taken back out, and everything a TA may edit still renders."""
        rendered = render_crispy_form(TAQuestForm())

        for field_name in TA_RESTRICTED_QUEST_FIELDS:
            with self.subTest(dropped=field_name):
                self.assertNotIn(f'name="{field_name}"', rendered)

        # fields from the layout's top level and from inside its Advanced accordion, so a
        # too-eager removal that emptied a nested group would be caught
        for field_name in ('name', 'xp', 'instructions', 'sort_order', 'blocking'):
            with self.subTest(kept=field_name):
                self.assertIn(f'name="{field_name}"', rendered)

    def test_TAQuestForm__posted_restricted_fields_cannot_change_a_quest(self):
        """A TA's POST claiming every restricted field leaves all of them as the teacher set
        them: an unbound field is one a ModelForm never writes to its instance."""
        quest = Quest.objects.create(
            name="Teacher's Quest",
            published=False,
            archived=True,
            available_outside_course=True,
            editor=self.ta,
        )

        form = TAQuestForm(
            data={
                **self.minimal_valid_data,
                'published': True,
                'archived': False,
                'available_outside_course': False,
                'editor': self.teacher.id,
            },
            instance=quest,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()

        self.assertFalse(saved.published)
        self.assertTrue(saved.archived)
        self.assertTrue(saved.available_outside_course)
        self.assertEqual(saved.editor, self.ta)

    def test_TAQuestForm__saves_the_editable_fields(self):
        """The restrictions don't stop a TA from doing their job: an ordinary edit still saves."""
        quest = Quest.objects.create(name="Draft", published=False, editor=self.ta)

        form = TAQuestForm(data={**self.minimal_valid_data, 'name': "Renamed by the TA"}, instance=quest)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()

        self.assertEqual(saved.name, "Renamed by the TA")


class QuickReplyFormsSanitizeHTMLTest(ByteDeckTenantTestCase):
    """The plain-text (non-wysiwyg) reply forms are accessible to all users and
    rendered with |safe. They carry rich HTML from the Summernote editor, so their
    `comment_text` is sanitized with an allow-list on cleaning: legitimate
    formatting is preserved (issue #2113) while scripts and event handlers are
    stripped so they can't execute (regression tests for issue #1343).
    """

    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    formatting_payload = '<p>hello <b>bold</b> <a href="http://example.com">link</a></p>'

    forms_under_test = (
        ('student quick reply', SubmissionQuickReplyFormStudent),
        ('staff quick reply', SubmissionQuickReplyForm),
        ('reply', SubmissionReplyForm),
    )

    def test_reply_forms__strip_scripts_and_event_handlers(self):
        """Scripts and inline event handlers are removed from every reply form so a
        crafted comment can't run JavaScript when rendered (issue #1343)."""
        for label, form_class in self.forms_under_test:
            with self.subTest(form=label):
                form = form_class(data={'comment_text': self.xss_payload})
                self.assertTrue(form.is_valid())
                cleaned = form.cleaned_data['comment_text']
                # the <script> tag is neutralized (escaped, not a live tag)...
                self.assertNotIn('<script>', cleaned)
                self.assertIn('&lt;script&gt;', cleaned)
                # ...and the onerror event handler is stripped off the surviving <img>
                self.assertNotIn('onerror', cleaned)

    def test_reply_forms__preserve_legitimate_formatting(self):
        """Ordinary formatting HTML survives sanitizing so rich comments render
        instead of showing their literal tags (issue #2113)."""
        for label, form_class in self.forms_under_test:
            with self.subTest(form=label):
                form = form_class(data={'comment_text': self.formatting_payload})
                self.assertTrue(form.is_valid())
                cleaned = form.cleaned_data['comment_text']
                self.assertIn('<b>bold</b>', cleaned)
                self.assertIn('<a href="http://example.com">link</a>', cleaned)
                self.assertIn('<p>', cleaned)
