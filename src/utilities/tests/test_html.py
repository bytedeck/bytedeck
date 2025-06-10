from django.test import SimpleTestCase
from html.parser import HTMLParser
from utilities.html import textify, urlize
from comments.models import clean_html


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
        and the URL text is preserved.
        """
        text = "Visit www.example.com"
        result = urlize(text)
        self.assertIn('<a href="http://www.example.com"', result)
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
        """
        url = "http://example.com/this/is/a/very/long/url/that/needs/trimming"
        trimmed_length = 30
        result = urlize(url, trim_url_limit=trimmed_length)

        expected_display = url[:trimmed_length].rstrip() + "..."

        # Parse visible text
        parser = LinkTextExtractor()
        parser.feed(result)
        visible_text = parser.get_text()

        self.assertTrue(result.startswith(f'<a href="{url}"'))
        self.assertEqual(visible_text, expected_display)

    def test_multiple_urls(self):
        """
        Test that multiple URLs in the input text are all converted into anchor tags.
        """
        text = "Links: http://foo.com and https://bar.com/page"
        result = urlize(text)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="https://bar.com/page"', result)
        self.assertEqual(result.count('<a '), 2)

    def test_no_trim(self):
        """
        Test that URLs shorter than trim_url_limit are not trimmed
        and the display text matches the full URL.
        """
        url = "http://short.url"
        result = urlize(url, trim_url_limit=100)
        self.assertIn(url, result)
        self.assertNotIn("...", result)

    def test_url_positions(self):
        self.assertIn('<a href="http://start.com"', urlize("http://start.com is at the start"))
        self.assertIn('<a href="http://middle.com"', urlize("Text before http://middle.com text after"))
        self.assertIn('<a href="http://end.com"', urlize("Ends with http://end.com"))

    def test_https_link(self):
        result = urlize("Check https://secure.com")
        self.assertIn('href="https://secure.com"', result)

    def test_non_url_text(self):
        text = "This is just a sentence. Not a link!"
        result = urlize(text)
        self.assertEqual(result, text)

    def test_trailing_punctuation(self):
        result = urlize("Visit http://example.com.")
        self.assertIn('href="http://example.com"', result)
        self.assertTrue(result.endswith("</a>."))

    def test_already_linked_html(self):
        html = '<a href="http://example.com">example</a>'
        result = urlize(html)
        self.assertEqual(result, html)

    def test_no_javascript_links(self):
        text = "Click javascript:alert('xss')"
        result = urlize(text)
        self.assertNotIn("href=", result)  # Should not linkify

    def test_display_text_preserved(self):
        url = "http://test.com"
        result = urlize(url)
        self.assertEqual(result, '<a href="http://test.com">http://test.com</a>')

    def test_clean_html_url_integration(self):
        """
        Ensure that clean_html applies urlize logic to plain text URLs.
        """
        text = "Go to www.example.com"
        result = clean_html(text)
        self.assertIn('<a href="http://www.example.com"', result)
        self.assertIn('target="_blank"', result)

    def test_clean_html_trims_long_urls(self):
        """
        Test that clean_html trims long URLs in display text.
        """
        url = "http://example.com/this/is/a/very/long/path/that/needs/to/be/trimmed"
        result = clean_html(url)
        self.assertIn("...", result)
        self.assertIn('href="http://example.com/this/is/a/very/long/path/that/needs/to/be/trimmed"', result)

    def test_clean_html_ignores_existing_links(self):
        """
        Test that clean_html doesn't re-process existing anchor tags.
        """
        html = '<a href="http://example.com">Click</a>'
        result = clean_html(html)
        self.assertEqual(result.count('<a '), 1)
        self.assertIn('href="http://example.com"', result)
        self.assertIn('target="_blank"', result)

    def test_clean_html_multiple_urls(self):
        """
        Ensure that multiple unformatted URLs are handled correctly.
        """
        html = "http://foo.com and www.bar.com"
        result = clean_html(html)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="http://www.bar.com"', result)
        self.assertEqual(result.count("<a "), 2)

    def test_clean_html_does_not_link_javascript(self):
        """
        Ensure javascript: links are not linkified.
        """
        text = "Check javascript:alert('XSS')"
        result = clean_html(text)
        self.assertNotIn('<a ', result)
