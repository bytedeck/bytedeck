from comments.forms import CommentForm
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class CommentFormTest(ByteDeckTenantTestCase):
    """The plain-text (non-wysiwyg) comment form is accessible to all users, so
    all HTML entered in it must be completely escaped. Regression tests for
    issue #1343 where scripts entered in plain-text comment fields would execute.
    """

    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    escaped_payload = ('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
                       '&lt;img src=x onerror=alert(1)&gt;')

    def test_comment_form__escapes_html_when_not_wysiwyg(self):
        """All HTML in the plain-text (default) comment form is escaped on cleaning."""
        form = CommentForm(data={'comment_text': self.xss_payload})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], self.escaped_payload)

    def test_comment_form__wysiwyg_html_untouched_by_form(self):
        """The wysiwyg variant leaves HTML alone at the form level: its content is
        sanitized by the safe summernote widget and `clean_html()` on save instead.
        """
        html = '<p>some <b>formatted</b> text</p>'
        form = CommentForm(data={'comment_text': html}, wysiwyg=True)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['comment_text'], html)
