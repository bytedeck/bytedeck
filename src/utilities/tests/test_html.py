from django.test import SimpleTestCase

from utilities.html import textify


class TestUtilsText(SimpleTestCase):
    """
    Various tests for `utilities.text` module.
    """

    def test_textify(self):
        """
        Generate a plain text version of an html content using html2text library.
        """
        html = """<p><strong>Zed's</strong> dead baby, <em>Zed's</em> dead.</p>"""
        output = textify(html)
        self.assertEqual(output, """**Zed's** dead baby, _Zed's_ dead.\n\n""")
