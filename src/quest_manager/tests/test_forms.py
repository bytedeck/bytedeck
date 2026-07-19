from django.utils import timezone

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from quest_manager.forms import (
    QuestForm,
    SubmissionQuickReplyForm,
    SubmissionQuickReplyFormStudent,
    SubmissionReplyForm,
)


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


class QuickReplyFormsEscapeHTMLTest(ByteDeckTenantTestCase):
    """The plain-text (non-wysiwyg) reply forms are accessible to all users, so
    all HTML entered in them must be completely escaped. Regression tests for
    issue #1343 where scripts entered in the quick reply form would execute.
    """

    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    escaped_payload = ('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
                       '&lt;img src=x onerror=alert(1)&gt;')

    def test_SubmissionQuickReplyFormStudent__escapes_html(self):
        """All HTML in the student quick reply form is escaped on cleaning."""
        form = SubmissionQuickReplyFormStudent(data={'comment_text': self.xss_payload})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], self.escaped_payload)

    def test_SubmissionQuickReplyForm__escapes_html(self):
        """All HTML in the staff quick reply form is escaped on cleaning."""
        form = SubmissionQuickReplyForm(data={'comment_text': self.xss_payload})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], self.escaped_payload)

    def test_SubmissionReplyForm__escapes_html(self):
        """All HTML in the reply form is escaped on cleaning."""
        form = SubmissionReplyForm(data={'comment_text': self.xss_payload})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], self.escaped_payload)
