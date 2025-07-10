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
# This checks if the text starts with a number or a single letter followed by a dot,
# such as "1." or "a.", and makes sure it is not immediately followed by a space.
# For example, it matches "1.example.com" or "a.example.com", but not "1. example.com".
# https://regex101.com/r/402DAE/1
LIST_PREFIX_RE = re.compile(r'^([0-9]+|[a-zA-Z])\.(?=[^\s])')


def urlize(text, trim_url_limit=None):
    """
    Converts plain text URLs into HTML anchor tags.

    - Optionally trims the display text of URLs if they exceed trim_url_limit.
    - Detects list prefixes like "1." or "a." at the start of the text and avoids linking them.
    - Skips processing if the text already contains an HTML anchor tag (<a href="...">).

    Args:
        text (str): The input text to process.
        trim_url_limit (int, optional): Maximum length for displayed URLs. If set, URLs longer than this will be trimmed.

    Returns:
        str: The processed HTML string with URLs converted to links.
    """

    if not text:
        return ""

    # Skip if already HTML links
    # If the text already contains an HTML anchor tag (<a href="...">),
    # skip further processing and return the text as-is.
    # This prevents double-linking or corrupting existing links.
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def trim(attrs, new):
        """
        Callback for bleach.linkify to optionally trim the display text of URLs.

        This is used to shorten the visible text of a hyperlink (i.e. what appears between <a>...</a>),
        without affecting the actual href. If the display text exceeds `trim_url_limit`, it is truncated
        and an ellipsis ("...") is appended.

        Example:
            Input string:
                "Check out this site: http://example.com/very/long/link"
            With trim_url_limit = 15:
                Output:
                'Check out this site: <a href="http://example.com/very/long/link">http://example....</a>'

        Args:
            attrs (dict): Attributes of the anchor tag. Contains '_text' (display text) and standard
                        link attributes like 'href', 'rel', etc.

        Returns:
            dict: Modified attributes where '_text' is trimmed if it exceeds the specified limit.
        """
        # Preserve all other attributes except the display text
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }
        display_text = attrs.get("_text", "")
        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            display_text = display_text[:trim_url_limit].rstrip() + "..."
        clean_attrs["_text"] = display_text
        return clean_attrs

    # Detect and split prefix like "1.test.com" or "a.test.com"
    match = LIST_PREFIX_RE.match(text)
    if match:
        prefix = match.group(0)  # "1." or "a."
        rest = text[len(prefix):]
        return prefix + bleach.linkify(rest, callbacks=[trim])

    return bleach.linkify(text, callbacks=[trim])
