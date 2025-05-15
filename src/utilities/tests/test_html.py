from django.test import SimpleTestCase
from html.parser import HTMLParser
from utilities.html import textify, urlize


class TestUtilsText(SimpleTestCase):
    """
    Various tests for `utilities.html` module.
    """

    def test_textify(self):
        """
        Generate a plain text version of an html content using html2text library.
        """
        html = """<p><strong>Zed's</strong> dead baby, <em>Zed's</em> dead.</p>"""
        output = textify(html)
        self.assertEqual(output, """**Zed's** dead baby, _Zed's_ dead.\n\n""")

    def test_textify_donot_ignore_links(self):
        """
        Don't ignore links anymore, I like links
        """
        html = """<p>Hello, <a href='https://www.google.com/earth/'>world</a>!</p>"""
        output = textify(html)
        self.assertEqual(output, """Hello, [world](https://www.google.com/earth/)!\n\n""")


class LinkTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.link_texts = []

    def handle_data(self, data):
        self.link_texts.append(data)

    def get_text(self):
        return "".join(self.link_texts)


class UrlizeTests(SimpleTestCase):
    def test_basic(self):
        """
        Test that a simple URL is correctly converted into an anchor tag
        with rel="nofollow" attribute and the URL text is preserved.
        """
        text = "Visit www.example.com"
        result = urlize(text)
        self.assertIn('<a href="http://www.example.com"', result)
        self.assertIn('rel="nofollow"', result)
        self.assertIn('www.example.com', result)

    def test_empty(self):
        """
        Test that empty string or None input returns an empty string without error.
        """
        self.assertEqual(urlize(""), "")
        self.assertEqual(urlize(None), "")

    def test_trim_url_limit(self):
        """
        Test that URLs longer than trim_url_limit are trimmed in the displayed
        text but keep the full URL in the href attribute.
        Also ensures rel="nofollow" is added.
        """
        url = "http://example.com/this/is/a/very/long/url/that/needs/trimming"
        trimmed_length = 30
        result = urlize(url, trim_url_limit=trimmed_length)

        expected_display = url[:trimmed_length].rstrip() + "..."

        # Parse visible text
        parser = LinkTextExtractor()
        parser.feed(result)
        visible_text = parser.get_text()

        self.assertIn('rel="nofollow"', result)
        self.assertTrue(result.startswith(f'<a href="{url}"'))
        self.assertEqual(visible_text, expected_display)

    def test_multiple_urls(self):
        """
        Test that multiple URLs in the input text are all converted into anchor tags,
        each with rel="nofollow".
        """
        text = "Links: http://foo.com and https://bar.com/page"
        result = urlize(text)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="https://bar.com/page"', result)
        self.assertEqual(result.count('<a '), 2)
        self.assertEqual(result.count('rel="nofollow"'), 2)

    def test_no_trim(self):
        """
        Test that URLs shorter than trim_url_limit are not trimmed
        and the display text matches the full URL.
        """
        url = "http://short.url"
        result = urlize(url, trim_url_limit=100)
        self.assertIn(url, result)
        self.assertNotIn("...", result)
