"""
HTML utilities suitable for global use, matching `django.utils.html` naming convention.
"""
# html2text is a python script that converts a page of HTML into clean, easy-to-read plain ASCII text
import html2text
import bleach
import html as html_module
import re

from django.utils.html import strip_tags

# Tags that are content in their own right, with no text of their own. A student can answer a
# question with nothing but a pasted screenshot or an embedded video, so `is_empty_html` has to
# see those as an answer even though stripping the tags leaves an empty string behind.
EMBEDDED_CONTENT_TAGS = frozenset({
    "img", "iframe", "video", "audio", "source", "track", "embed", "object", "svg", "canvas", "math",
})

# The name of each opening tag in a fragment, e.g. "<p><img src='x'>" -> ["p", "img"]. Only text
# outside a tag can be escaped, so an `&lt;img&gt;` the user typed is never matched here.
_OPENING_TAG_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9:-]*)")


def is_empty_html(value):
    """Whether a fragment of user-authored HTML holds nothing a reader would see.

    The Summernote editor never submits an empty string: an editor a student clicked into and
    left alone posts ``<p><br></p>``, and one they typed a space into posts ``<p>&nbsp;</p>``.
    Both are truthy, so a plain ``if not value`` check reads them as content and lets a blank
    answer through a required field (#2560). Tags and entities are removed and the remainder
    tested for any non-whitespace character (``&nbsp;`` decodes to ``\xa0``, which ``strip()``
    counts as whitespace).

    The question asked is deliberately "is this definitely empty?", not "is this content?".
    Anything uncertain is reported as non-empty, because refusing an answer a student really
    gave is far worse than accepting a blank one: hence `EMBEDDED_CONTENT_TAGS`, which answers
    False for a fragment whose whole content is a picture or an embed.

    Args:
        value: HTML from a rich-text editor, or None/empty for a field never filled in.

    Returns:
        bool: True when the fragment would render as nothing.
    """
    if not value:
        return True

    text = str(value)

    tags = {name.lower() for name in _OPENING_TAG_RE.findall(text)}
    if tags & EMBEDDED_CONTENT_TAGS:
        return False

    # unescape after stripping, so an entity standing alone ("&nbsp;") is judged as the
    # character it renders as rather than as the seven literal characters that spell it
    return not html_module.unescape(strip_tags(text)).strip()


def textify(html):
    """
    Generate a plain text version of an html content using html2text library.
    """
    h = html2text.HTML2Text()
    # don't ignore links anymore, I like links
    h.ignore_links = False
    return h.handle(html)


# Regular expression to match list prefixes like "1." or "a."
# This checks if the line starts with a number or a single letter followed by a dot,
# and makes sure it is immediately followed by a non-space character.
# For example, it matches "1.example.com" or "a.example.com" but not "1. example.com".
# https://regex101.com/r/402DAE/1
LIST_PREFIX_RE = re.compile(r'^([0-9]+|[a-zA-Z])\.(?=\S)')


def urlize(text, trim_url_limit=None):
    """
    Linkify URLs in text while preserving list prefixes and working with <br>-separated HTML.

    - Preserves numeric or alphabetic list prefixes (e.g. "1.", "a.") outside of links.
    - Handles input text where newlines have been replaced by <br> tags.
    - Skips linkifying if the input already contains HTML links.
    - Optionally trims the display text of links longer than `trim_url_limit`.

    Args:
        text (str): The input text or HTML to linkify.
        trim_url_limit (int, optional): Maximum length for visible URL text, truncates if exceeded.

    Returns:
        str: Text with URLs converted to HTML anchor tags, preserving prefixes.
    """

    if not text:
        return ""

    # Skip processing if text already contains an HTML anchor tag,
    # to avoid double-linking or corrupting existing links.
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def trim(attrs, new):
        """
        bleach.linkify callback to optionally trim visible URL text.

        Preserves all anchor tag attributes except '_text' which is trimmed
        and appended with "..." if it exceeds the trim_url_limit.

        Args:
            attrs (dict): Attributes of the anchor tag, including '_text' as display text.
            new (bool): Indicates if the link is newly created (unused here).

        Returns:
            dict: Modified attributes with trimmed '_text' if necessary.
        """
        # Keep all attributes except '_text' unchanged
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }
        display_text = attrs.get("_text", "")
        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            # Trim and append ellipsis if display text is too long
            display_text = display_text[:trim_url_limit] + "..."
        clean_attrs["_text"] = display_text
        return clean_attrs

    # Split input text by <br> tags, which represent line breaks after cleaning.
    parts = text.split('<br>')
    processed_parts = []

    # Process each line separately to detect and preserve list prefixes
    for part in parts:
        match = LIST_PREFIX_RE.match(part)
        prefix = match.group(0) if match else ''  # Extract prefix like "1." or "a.", if present
        rest = part[len(prefix):] if match else part  # The rest of the line after the prefix
        # Linkify the remainder, then prepend the prefix (if any)
        processed = prefix + bleach.linkify(rest, callbacks=[trim])
        processed_parts.append(processed)

    # Rejoin lines with <br> to preserve original formatting
    return '<br>'.join(processed_parts)
