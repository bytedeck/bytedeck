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
    Converts plain text URLs into HTML anchor tags using bleach.linkify.
    Adds rel="nofollow" to all links and optionally trims displayed text.
    Existing <a href="..."> HTML is left untouched.
    """
    if not text:
        return ""

    # Skip transformation if HTML anchor tags already exist
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def add_nofollow_and_trim(attrs, new):
        # Extract display text if present
        display_text = attrs.get('_text', '')
        cleaned_attrs = {}

        # Normalize attribute keys to (namespace, name) tuples
        for key, value in attrs.items():
            if key == '_text':
                continue
            if isinstance(key, tuple):
                cleaned_attrs[key] = value
            else:  # key is a plain string
                cleaned_attrs[(None, key)] = value

        # Always add rel="nofollow"
        cleaned_attrs[(None, "rel")] = "nofollow"

        # Optionally trim the display text
        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            cleaned_attrs["_text"] = display_text[:trim_url_limit].rstrip() + "..."

        return cleaned_attrs  # Must be a dict only

    return bleach.linkify(text, callbacks=[add_nofollow_and_trim])
