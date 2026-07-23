"""Shared sanitization for user-entered comment HTML.

Comment bodies are rendered with Django's ``|safe`` filter, so whatever is
stored is emitted as-is into the page. The plain-text / quick-reply comment
forms are reachable by every user (including students), and in practice they
receive rich HTML from the Summernote editor rather than literal plain text.

Issue #1343 originally locked these fields down by ``escape()``-ing *all* HTML,
but that also escaped legitimate formatting, so a normal comment like
``<p>hello</p>`` rendered as the literal text ``<p>hello</p>`` (issue #2113).

The fix is to sanitize with an allow-list instead of escaping everything:
legitimate formatting tags are kept (so comments render), while ``<script>``,
inline event-handler attributes (``onclick``/``onerror``/...), and
``javascript:`` URLs are stripped, so a crafted comment still can't run script.
This reuses the same tag/style allow-list as the "safe" Summernote widget, but
with a stricter attribute policy that drops event handlers (the Summernote
widget currently allows all attributes).
"""

import bleach

from bytedeck_summernote.css_sanitizer import CSSSanitizer
from bytedeck_summernote.settings import ALLOWED_TAGS, STYLES

# Attributes that must never survive sanitization regardless of tag: inline
# event handlers (any ``on*``) and a few attributes that can smuggle script or
# hijack forms.
_DISALLOWED_ATTRIBUTES = {"srcdoc", "formaction", "form", "xlink:href"}


def _allow_attribute(tag, name, value):
    """bleach attribute filter: allow anything except event handlers and a small
    deny-list of dangerous attributes, so sanitized comment HTML can't carry
    inline JavaScript."""
    name = name.lower()
    if name.startswith("on"):
        return False
    return name not in _DISALLOWED_ATTRIBUTES


def sanitize_comment_html(text):
    """Return ``text`` with dangerous HTML removed but safe formatting preserved.

    Keeps the Summernote allow-list of formatting tags/styles so rich comments
    render (issue #2113), while stripping ``<script>``, ``on*`` event-handler
    attributes, and ``javascript:`` URLs so a crafted comment can't execute when
    displayed with ``|safe`` (issue #1343).
    """
    return bleach.clean(
        text or "",
        tags=ALLOWED_TAGS,
        attributes=_allow_attribute,
        css_sanitizer=CSSSanitizer(allowed_css_properties=STYLES),
    )
