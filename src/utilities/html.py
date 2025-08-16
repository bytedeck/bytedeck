"""
HTML utilities suitable for global use, matching `django.utils.html` naming convention.
"""
# html2text is a python script that converts a page of HTML into clean, easy-to-read plain ASCII text
import html2text
import bleach
import re


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
