import re
import unittest

from quest_manager.signals import tidy_html


class TestTidyHtml(unittest.TestCase):
    def test_tidy_html__with_no_inline_tags(self):
        """ Html is indented 4 spaces"""
        # Given
        markup = "<div><p>Hello, world!</p></div>"

        # When
        result = tidy_html(markup)

        # Then
        expected = "<div>\n  <p>\n    Hello, world!\n  </p>\n</div>"
        self.assertEqual(result, expected)

    def test_tidy_html__with_inline_tags(self):
        """inline tags such as <b> and <span> should not be indented"""
        # Given
        markup = "<div><p><b>Hello</b>, <span>world</span>!</p></div>"

        # When
        result = tidy_html(markup)

        # Then
        expected = "<div>\n  <p>\n    <b>Hello</b>, <span>world</span>!\n  </p>\n</div>"
        self.assertEqual(result, expected)

    def test_tidy_html__formatting_math(self):
        markup = r"""<span class="note-math"><span class="katex"><span class="katex-mathml"><math><semantics><mrow><mrow><mi>x</mi></mrow></mrow><annotation encoding="application/x-tex">{x}</annotation></semantics></math></span>"""  # noqa
        result = tidy_html(markup)
        self.assertIn(markup, result)

        matches_found = re.search('({{)|(}})', result)
        self.assertIsNone(matches_found)

    def test_quest_html_formatting_tabs(self):
        markup_tests = [  # test, expected out come
            ("<p>some text</p>", "<p>\n  some text\n</p>"),
            ("<p>some text\n\n</p>", "<p>\n  some text\n</p>"),
            ("<p>some \ntext</p>", "<p>\n  some \ntext\n</p>"),
            ("<p>some \n text</p>", "<p>\n  some \n text\n</p>"),
            ("<ol><li>test</li></ol>", "<ol>\n  <li>\n    test\n  </li>\n</ol>"),
            (" <p>", "<p>\n</p>"),  # fix unclosed paragraphs
            ('<img src="\n example.png">', '<img src="\n example.png"/>\n'),  # don't indent within properties
            ('<img src="example.png\n">', '<img src="example.png\n"/>\n'),  # don't indent within properties
            ('<ol><li>text', "<ol>\n  <li>\n    text\n  </li>\n</ol>"),  # fix unclosed lists
            ('<script>alert("Hello")</script>', '<script>\n  alert("Hello")\n</script>'),  # don't strip scripts here
            # standard Youtube embed
            ('<div class="embed-responsive embed-responsive-16by9" style="float: none;"><iframe src="//www.youtube.com/embed/dQw4w9WgXcQ?rel=0&amp;loop=0" allowfullscreen="true" class="embed-responsive note-video-clip" width="auto" height="auto" frameborder="0"></iframe></div>',  # noqa
             '<div class="embed-responsive embed-responsive-16by9" style="float: none;">\n  <iframe allowfullscreen="true" class="embed-responsive note-video-clip" frameborder="0" height="auto" src="//www.youtube.com/embed/dQw4w9WgXcQ?rel=0&loop=0" width="auto">\n  </iframe>\n</div>'),  # noqa
            ('', '')
        ]

        for pair in markup_tests:
            markup = pair[0]
            formatted_markup = tidy_html(markup)
            self.assertEqual(formatted_markup, pair[1])
