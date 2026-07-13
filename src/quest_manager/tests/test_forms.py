from django.utils import timezone

from django_tenants.test.cases import TenantTestCase

from quest_manager.forms import (
    QuestForm,
    SubmissionQuickReplyForm,
    SubmissionQuickReplyFormStudent,
    SubmissionReplyForm,
)


class QuestFormTest(TenantTestCase):

    def setUp(self):
        self.minimal_valid_data = {
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

    def test_minimal_valid_data(self):
        """The minimal_valid_data provided in the setup method should be valid!"""
        form = QuestForm(data=self.minimal_valid_data)
        self.assertTrue(form.is_valid())

    def test_hideable_blocking_both_true(self):
        """If a quest is Blocking then it should not validate if it is also Hideable"""
        form_data = self.minimal_valid_data

        form_data["hideable"] = True
        form_data["blocking"] = True

        form = QuestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("Blocking quests cannot be Hideable.", form.errors['__all__'][0])


class QuickReplyFormsEscapeHTMLTest(TenantTestCase):
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
