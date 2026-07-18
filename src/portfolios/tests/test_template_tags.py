from django.test import SimpleTestCase

from portfolios.templatetags.portfolio_tags import youthumb


class YouthumbFilterTest(SimpleTestCase):
    """Tests for the youthumb template filter that builds YouTube thumbnail urls."""

    URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

    def test_default_returns_small_thumb(self):
        self.assertEqual(youthumb(self.URL, ''), "http://img.youtube.com/vi/dQw4w9WgXcQ/2.jpg")

    def test_large_arg_returns_large_thumb(self):
        self.assertEqual(youthumb(self.URL, 'l'), "http://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg")
