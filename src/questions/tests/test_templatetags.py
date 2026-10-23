from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from questions.models import QuestionType
from questions.templatetags.question_tags import media_kind, plain_text, question_type_icon, unwrap_p


class UnwrapPTest(SimpleTestCase):
    """Tests for the ``unwrap_p`` template filter, which strips a single wrapping <p> from
    summernote-authored HTML so a one-line prompt/note can render inline after a label."""

    def test_unwrap_p__strips_single_paragraph(self):
        """A single wrapping <p>...</p> is removed so the content can sit inline."""
        self.assertEqual(unwrap_p("<p>What is your website URL?</p>"), "What is your website URL?")

    def test_unwrap_p__strips_paragraph_with_attributes(self):
        """The wrapping <p> is stripped even when it carries attributes."""
        self.assertEqual(unwrap_p('<p style="text-align:center">Centred</p>'), "Centred")

    def test_unwrap_p__preserves_inner_formatting(self):
        """Inline formatting inside the paragraph (bold, links) is kept."""
        self.assertEqual(
            unwrap_p('<p>See <a href="https://example.com">this</a> <b>now</b></p>'),
            'See <a href="https://example.com">this</a> <b>now</b>',
        )

    def test_unwrap_p__leaves_plain_text_unchanged(self):
        """Content without a wrapping <p> (e.g. a plain-text answer) is returned as-is."""
        self.assertEqual(unwrap_p("just text"), "just text")

    def test_unwrap_p__leaves_multiple_paragraphs_unchanged(self):
        """Multi-paragraph content has nothing sensible to inline, so it is left untouched."""
        html = "<p>first</p><p>second</p>"
        self.assertEqual(unwrap_p(html), html)

    def test_unwrap_p__handles_empty_value(self):
        """An empty string is returned unchanged (no crash on falsy input)."""
        self.assertEqual(unwrap_p(""), "")

    def test_unwrap_p__result_is_marked_safe(self):
        """A stripped result is marked safe so the template renders the HTML rather than escaping it."""
        self.assertIsInstance(unwrap_p("<p>hi</p>"), SafeString)


class QuestionTypeIconTest(SimpleTestCase):
    """Tests for the ``question_type_icon`` filter, which maps a question type to its FA icon."""

    def test_question_type_icon__each_type_has_an_icon(self):
        """Every question type maps to a distinct Font Awesome icon class."""
        self.assertEqual(question_type_icon(QuestionType.SHORT_ANSWER), "fa-i-cursor")
        self.assertEqual(question_type_icon(QuestionType.LONG_ANSWER), "fa-align-left")
        self.assertEqual(question_type_icon(QuestionType.FILE_UPLOAD), "fa-paperclip")

    def test_question_type_icon__matches_stored_string_value(self):
        """The stored ``type`` value (a plain string, as read off a model) resolves too."""
        self.assertEqual(question_type_icon("short_answer"), "fa-i-cursor")

    def test_question_type_icon__unknown_type_is_blank(self):
        """An unrecognised type yields an empty class rather than raising."""
        self.assertEqual(question_type_icon("mystery"), "")


class PlainTextTest(SimpleTestCase):
    """Tests for the ``plain_text`` filter, which reduces summernote HTML to the text a teacher
    typed so it can go in a tooltip or a table cell."""

    def test_plain_text__strips_tags(self):
        """Markup around the text is removed."""
        self.assertEqual(plain_text("<p>What is your <b>website</b> URL?</p>"), "What is your website URL?")

    def test_plain_text__decodes_entities(self):
        """Entities become the characters they stand for, so escaping happens once, not twice.

        Summernote stores an ampersand as ``&amp;``. Left encoded, the template escapes it again
        and the tooltip reads "Tom &amp;amp; Jerry" instead of the title the teacher typed.
        """
        self.assertEqual(plain_text("<p>Tom &amp; Jerry &lt;3</p>"), "Tom & Jerry <3")

    def test_plain_text__image_only_instructions_are_empty(self):
        """Instructions that are only an image reduce to nothing, which the template shows as a dash."""
        self.assertEqual(plain_text('<p><img src="/media/x.png"></p>'), "")

    def test_plain_text__handles_empty_value(self):
        """None and empty strings come back as an empty string rather than raising."""
        self.assertEqual(plain_text(None), "")
        self.assertEqual(plain_text(""), "")

    def test_plain_text__result_is_not_marked_safe(self):
        """The result stays escapable, so a stray quote cannot break out of a title attribute."""
        self.assertNotIsInstance(plain_text('<p>a " quote</p>'), SafeString)


class MediaKindFilterTest(SimpleTestCase):
    """Tests for the ``media_kind`` filter, which the answer display uses to embed a file."""

    def test_media_kind__reads_a_file_fields_name(self):
        """The filter is handed a file field's value, and answers from the name it stores."""
        self.assertEqual(media_kind(SimpleNamespace(name="answers/2026/my_drawing.png")), "image")

    def test_media_kind__is_empty_for_no_file(self):
        """A question with nothing uploaded answers with the empty string, not an error.

        Every file field on a question is optional, so the template asks about plenty of
        empty ones; `None` and an unset `FieldFile` are both falsy, hence one check.
        """
        self.assertEqual(media_kind(None), "")
        self.assertEqual(media_kind(""), "")
