from comments.forms import CommentForm
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class CommentFormTest(ByteDeckTenantTestCase):
    """The plain-text (non-wysiwyg) comment form is accessible to all users and
    rendered with |safe, so its HTML is sanitized with an allow-list on cleaning:
    legitimate formatting is preserved (issue #2113) while scripts and event
    handlers are stripped so they can't execute (regression tests for issue #1343).
    """

    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    formatting_payload = '<p>hello <b>bold</b> <a href="http://example.com">link</a></p>'

    def test_comment_form__strips_scripts_and_event_handlers_when_not_wysiwyg(self):
        """Scripts and event handlers are removed from the plain-text (default) comment
        form so injected JavaScript can't execute (issue #1343)."""
        form = CommentForm(data={'comment_text': self.xss_payload})
        self.assertTrue(form.is_valid())
        cleaned = form.cleaned_data['comment_text']
        self.assertNotIn('<script>', cleaned)
        self.assertIn('&lt;script&gt;', cleaned)
        self.assertNotIn('onerror', cleaned)

    def test_comment_form__preserves_formatting_when_not_wysiwyg(self):
        """Legitimate formatting HTML survives sanitizing so comments render instead
        of showing their literal tags (issue #2113)."""
        form = CommentForm(data={'comment_text': self.formatting_payload})
        self.assertTrue(form.is_valid())
        cleaned = form.cleaned_data['comment_text']
        self.assertIn('<b>bold</b>', cleaned)
        self.assertIn('<a href="http://example.com">link</a>', cleaned)

    def test_comment_form__wysiwyg_html_untouched_by_form(self):
        """The wysiwyg variant leaves HTML alone at the form level: its content is
        sanitized by the safe summernote widget and `clean_html()` on save instead.
        """
        html = '<p>some <b>formatted</b> text</p>'
        form = CommentForm(data={'comment_text': html}, wysiwyg=True)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], html)
