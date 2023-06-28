from django.test import SimpleTestCase

from utilities.html import textify


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
