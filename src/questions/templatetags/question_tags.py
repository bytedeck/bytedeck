import html
import os
import re

from django import template
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from questions.models import QuestionType
from utilities.fields import media_kind_of

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
def is_displayable_svg(value):
    """Whether a stored file is an SVG a page can safely show through an ``<img>``.

    An SVG reaches the site only as an answer to a question whose teacher ticked the
    script-capable opt-in, and it is never linked at its storage URL, because navigating to one
    runs any script it carries (#2559). Loaded as an image it is safe: browsers run no script,
    no external reference and no interactivity in SVG-as-image mode, whatever the file
    contains. So a graphic design student's artwork can still be looked at rather than only
    downloaded.

    ``.svgz`` is excluded deliberately: it is gzipped, and only renders where the storage
    serves it with ``Content-Encoding: gzip``, which is not something this app controls.

    Args:
        value: a stored file (any object whose ``name`` is its path), or None.

    Returns:
        bool: True for a file named ``.svg``.
    """
    name = getattr(value, "name", "") or ""
    return os.path.splitext(name.lower())[1] == ".svg"


@register.filter
def question_type_icon(question_type):
    """Return the Font Awesome icon class for a question's ``type`` (empty string if unknown)."""
    return _TYPE_ICONS.get(question_type, "")


@register.filter
def media_kind(value):
    """Return how a question's stored file can be shown: 'image', 'video', 'audio' or ''.

    A marker reading a set of answers should see the picture, not a filename to download and
    open (#2172), so the answer display asks each file what it is and embeds it accordingly.
    Anything else, and anything with no file, answers with the empty string and is offered
    as a link.

    Args:
        value: a file field's value (a `FieldFile`), or None/empty when nothing was uploaded.

    Returns:
        str: the kind of media, or '' when it is not one this page can embed.
    """
    if not value:
        return ''

    return media_kind_of(value.name)


@register.filter
def plain_text(value):
    """Reduce summernote-authored HTML to the text a teacher actually typed.

    Stripping tags on its own leaves the entities behind, so a question about "Tom & Jerry"
    becomes ``Tom &amp; Jerry``, and autoescaping where it lands turns that into a visible
    ``Tom &amp;amp; Jerry`` (#2169). Decoding after stripping gives back the characters
    themselves. The result is deliberately left unsafe, so the template escapes it once, which
    is what keeps it from breaking out of a title attribute.

    Args:
        value: summernote-authored HTML, or None for a field that was never filled in.

    Returns:
        str: the decoded text, unmarked, for the template to escape once where it lands.
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
    ``<p>``) is returned unchanged. The values this runs on (a question's instructions and its
    marker notes) are staff-authored, through the teacher's own question form, so their HTML is
    trusted the way the rest of a quest's rich text is and the result is marked safe.
    """
    if not value:
        return value
    text = str(value)
    match = _SINGLE_PARAGRAPH.match(text)
    if match and "<p" not in match.group("inner").lower():
        text = match.group("inner")
    return mark_safe(text)
