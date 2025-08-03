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

        Tests various scenarios:
        - Plain URL conversion
        - URLs preceded by numeric prefixes (e.g., "1.www.example.com")
        - URLs preceded by alphabetic prefixes (e.g., "a.www.example.com")
        - Both www and http protocol variants

        Verifies that prefixes remain outside the anchor tag href attribute.
        """
        text = "Visit www.example.com"
        result = urlize(text)
        self.assertIn('<a href="http://www.example.com"', result)
        self.assertIn('www.example.com', result)

        text = "1.www.example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('1.<a href="http://www.example.com"'))

        text = "a.www.example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('a.<a href="http://www.example.com"'))

        text = "1.http://example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('1.<a href="http://example.com"'))

        text = "a.http://example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('a.<a href="http://example.com"'))

    def test_empty(self):
        """
        Test that empty string or None input returns an empty string without error.

        Parameters tested:
        - Empty string ("")
        - None value

        Expected behavior: Both should return empty string without raising exceptions.
        """
        self.assertEqual(urlize(""), "")
        self.assertEqual(urlize(None), "")

    def test_trim_url_limit(self):
        """
        Test that long URLs are visually trimmed in the anchor text,
        while the href attribute retains the full URL.

        Test cases:
        - Long URL with custom trim_url_limit
        - Short URL with a large limit (no trimming expected)
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

        # Test no trim
        url = "http://short.url"
        result = urlize(url, trim_url_limit=100)
        self.assertIn(url, result)
        self.assertNotIn("...", result)

    def test_multiple_urls(self):
        """
        Test that multiple URLs in the input text are all converted into anchor tags.

        Input: Text containing two different URLs with different protocols
        Expected: Both URLs should be converted to separate anchor tags
        Verifies: Correct href attributes and proper count of anchor elements
        """
        text = "Links: http://foo.com and https://bar.com/page"
        result = urlize(text)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="https://bar.com/page"', result)
        self.assertEqual(result.count('<a '), 2)

    def test_url_positions(self):
        """
        Test that URLs are correctly linkified regardless of their position
        in the input string (start, middle, or end).

        Test cases:
        - URL at the beginning of the string
        - URL in the middle with surrounding text
        - URL at the end of the string

        Verifies: Proper href attribute generation for all positions
        """
        self.assertIn('<a href="http://start.com"', urlize("http://start.com is at the start"))
        self.assertIn('<a href="http://middle.com"', urlize("Text before http://middle.com text after"))
        self.assertIn('<a href="http://end.com"', urlize("Ends with http://end.com"))

    def test_non_url_text(self):
        """
        Test that plain text without any URLs is returned unmodified.
        """
        text = "This is just a sentence. Not a link!"
        result = urlize(text)
        self.assertEqual(result, text)

    def test_trailing_punctuation(self):
        """
        Test that trailing punctuation such as periods is excluded
        from the anchor tag.

        Input: "Visit http://example.com."
        Expected: Anchor ends before period, period remains outside
        """
        result = urlize("Visit http://example.com.")
        self.assertIn('href="http://example.com"', result)
        self.assertTrue(result.endswith("</a>."))

    def test_already_linked_html(self):
        """
        Test that pre-existing <a> tags are preserved and not double-processed.

        Security consideration: Prevents nested anchor tags which would create
        invalid HTML and potential security vulnerabilities.

        Input: HTML string containing existing anchor tag
        Expected: Original HTML returned unchanged
        """
        html = '<a href="http://example.com">example</a>'
        result = urlize(html)
        self.assertEqual(result, html)

    def test_no_javascript_links(self):
        """
        Test that javascript: links are not linkified for security reasons.
        """
        text = "Click javascript:alert('xss')"
        result = urlize(text)
        self.assertNotIn("href=", result)  # Should not linkify

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

    def test_numbered_list_with_br(self):
        # Input simulating comment input with <br> instead of newlines
        input_text = (
            "1.www.testing.com<br>"
            "2.www.example.com<br>"
            "3.www.notarealsite.com<br>"
            "4.testing.com<br>"
            "5.example.com"
        )

        result = urlize(input_text)

        # Make sure each prefix is outside the <a> tag
        self.assertTrue(result.startswith('1.<a href="http://www.testing.com"'))
        self.assertIn('2.<a href="http://www.example.com"', result)
        self.assertIn('3.<a href="http://www.notarealsite.com"', result)
        self.assertIn('4.<a href="http://testing.com"', result)
        self.assertIn('5.<a href="http://example.com"', result)

        # Ensure prefixes are NOT inside the links
        self.assertNotIn('<a href="http://1.', result)
        self.assertNotIn('<a href="http://2.', result)
