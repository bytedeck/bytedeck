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

    # Avoid double-linkification if already linked
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def add_nofollow_and_trim(attrs, new):
        # Extract visible link text
        display_text = attrs.get('_text', '')

        # Normalize attribute keys
        cleaned_attrs = {
            (None, key) if not isinstance(key, tuple) else key: val
            for key, val in attrs.items()
            if key != '_text'
        }

        # Add rel="nofollow"
        cleaned_attrs[(None, 'rel')] = 'nofollow'

        # Return (attrs, trimmed_text) if we want to override display text
        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            trimmed = display_text[:trim_url_limit].rstrip() + "..."
            return cleaned_attrs, trimmed

        # Otherwise return just the attrs dict — Bleach uses original _text
        return cleaned_attrs

    return bleach.linkify(text, callbacks=[add_nofollow_and_trim])
