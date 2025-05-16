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


def urlize(text, trim_url_limit=None):
    """
    Converts plain text URLs into HTML anchor tags.
    Adds rel="nofollow" and optionally trims display text.
    Returns early if the text already contains an <a> tag.
    """

    if not text:
        return ""

    # Skip if already HTML links
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text  # Already contains an anchor tag

    def add_nofollow_and_trim(attrs, new):
        # Create clean dict with namespace-correct keys
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }

        # Add rel="nofollow"
        clean_attrs[(None, "rel")] = "nofollow"

        # Always preserve the display text
        display_text = attrs.get("_text", "")

        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            display_text = display_text[:trim_url_limit].rstrip() + "..."

        # Critical: Add display text back to dict
        clean_attrs["_text"] = display_text

        return clean_attrs

    return bleach.linkify(text, callbacks=[add_nofollow_and_trim])
