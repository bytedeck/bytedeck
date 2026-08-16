import html
import re

from django import template
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from questions.models import QuestionType

register = template.Library()

# Font Awesome (4.7) icon class for each question type, shown beside a numbered answer so a
# marker can tell an answer's shape at a glance: a text cursor for a single-line short answer,
# paragraph lines for a long answer, a paperclip for a file upload.
_TYPE_ICONS = {
    QuestionType.SHORT_ANSWER: "fa-i-cursor",
    QuestionType.LONG_ANSWER: "fa-align-left",
    QuestionType.FILE_UPLOAD: "fa-paperclip",
}


@register.filter
def question_type_icon(question_type):
    """Return the Font Awesome icon class for a question's ``type`` (empty string if unknown)."""
    return _TYPE_ICONS.get(question_type, "")


@register.filter
def plain_text(value):
    """Reduce summernote-authored HTML to the text a teacher actually typed.

    Stripping tags on its own leaves the entities behind, so a question about "Tom & Jerry"
    becomes ``Tom &amp; Jerry``, and autoescaping where it lands turns that into a visible
    ``Tom &amp;amp; Jerry`` (#2169). Decoding after stripping gives back the characters
    themselves. The result is deliberately left unsafe, so the template escapes it once, which
    is what keeps it from breaking out of a title attribute.
    """
    return html.unescape(strip_tags(value or ""))

# Matches content that is a single wrapping <p>...</p> (optionally with attributes and
# surrounding whitespace). The inner group is only unwrapped when it contains no further
# <p, so multi-paragraph content is left untouched (there's nothing sensible to inline).
_SINGLE_PARAGRAPH = re.compile(r"^\s*<p(?:\s[^>]*)?>(?P<inner>.*)</p>\s*$", re.DOTALL | re.IGNORECASE)


@register.filter
def unwrap_p(value):
    """Strip a single wrapping ``<p>...</p>`` from summernote-authored HTML so it can flow
    inline after a label (e.g. a question's "Question N:" heading, or a "Marker notes:" label)
    instead of dropping onto its own line.

    The Summernote editor wraps even one line of text in a ``<p>``; nesting that block inside an
    inline context (``<small>``, ``<span>``) makes the browser reparent it onto a new line, so
    removing the wrapper is what actually keeps it inline. Multi-paragraph content (an inner
    ``<p>``) is returned unchanged. The value is assumed already sanitized — these fields are
    teacher-authored and were previously rendered with ``|safe`` — so the result is marked safe.
    """
    if not value:
        return value
    text = str(value)
    match = _SINGLE_PARAGRAPH.match(text)
    if match and "<p" not in match.group("inner").lower():
        text = match.group("inner")
    return mark_safe(text)
