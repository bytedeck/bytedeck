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


LIST_PREFIX_RE = re.compile(r'^([0-9]+|[a-zA-Z])\.(?=[^\s])')


def urlize(text, trim_url_limit=None):
    """
    Converts plain text URLs into HTML anchor tags.
    Adds rel="nofollow" and optionally trims display text.
    Detects list prefixes like "1." or "a." and avoids linking them.
    """

    if not text:
        return ""

    # Skip if already HTML links
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def add_nofollow_and_trim(attrs, new):
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }
        # clean_attrs[(None, "rel")] = "nofollow" # Uncomment if you want to add rel="nofollow"
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
        return prefix + bleach.linkify(rest, callbacks=[add_nofollow_and_trim])

    return bleach.linkify(text, callbacks=[add_nofollow_and_trim])


LIST_PREFIX_RE = re.compile(r'^([0-9]+|[a-zA-Z])\.(?=[^\s])')


def urlize(text, trim_url_limit=None):
    """
    Converts plain text URLs into HTML anchor tags.
    Adds rel="nofollow" and optionally trims display text.
    Detects list prefixes like "1." or "a." and avoids linking them.
    """

    if not text:
        return ""

    # Skip if already HTML links
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def add_nofollow_and_trim(attrs, new):
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }
        # clean_attrs[(None, "rel")] = "nofollow"
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
        return prefix + bleach.linkify(rest, callbacks=[add_nofollow_and_trim])

    return bleach.linkify(text, callbacks=[add_nofollow_and_trim])
