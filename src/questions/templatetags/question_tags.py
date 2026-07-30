import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

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
