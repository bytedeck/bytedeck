from django.test import SimpleTestCase

from comments.sanitize import sanitize_comment_html


class SanitizeCommentHTMLTest(SimpleTestCase):
    """Unit tests for the shared comment-HTML sanitizer (issues #1343 / #2113)."""

    def test_preserves_legitimate_formatting(self):
        """Ordinary formatting tags survive so rich comments render (issue #2113)."""
        html = '<p>hi <b>bold</b> <a href="http://example.com">link</a></p><ul><li>a</li></ul>'
        cleaned = sanitize_comment_html(html)
        self.assertIn('<b>bold</b>', cleaned)
        self.assertIn('<a href="http://example.com">link</a>', cleaned)
        self.assertIn('<li>a</li>', cleaned)

    def test_strips_script_tag(self):
        """<script> is neutralized so it can't execute (issue #1343)."""
        cleaned = sanitize_comment_html('<script>alert(1)</script>')
        self.assertNotIn('<script>', cleaned)
        self.assertIn('&lt;script&gt;', cleaned)

    def test_strips_event_handler_attributes(self):
        """Inline event handlers (on*) are removed from otherwise-allowed tags."""
        cleaned = sanitize_comment_html('<img src=x onerror=alert(1)>')
        self.assertNotIn('onerror', cleaned)
        self.assertIn('<img', cleaned)  # the tag itself is allowed, only the handler is dropped

    def test_strips_denylisted_attributes(self):
        """Explicitly denied attributes (e.g. srcdoc) are stripped even on allowed tags."""
        cleaned = sanitize_comment_html('<iframe srcdoc="<script>alert(1)</script>"></iframe>')
        self.assertNotIn('srcdoc', cleaned)

    def test_strips_javascript_url(self):
        """javascript: URLs are removed from links."""
        cleaned = sanitize_comment_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn('javascript:', cleaned)

    def test_none_and_empty_are_safe(self):
        """None / empty input sanitize to an empty string without error."""
        self.assertEqual(sanitize_comment_html(None), '')
        self.assertEqual(sanitize_comment_html(''), '')
