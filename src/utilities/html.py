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
    Adds rel="nofollow" attribute to anchor tags while correctly handling
    attribute keys and avoiding serializer errors.
    """
    if not text:
        return ""

    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text  # Optional: skip if already HTML

    def nofollow(attrs, new):
        clean_attrs = {}

        # Extract display text
        display_text = attrs.get('_text', '')

        for k, v in attrs.items():
            if k == '_text':
                continue
            # Keep tuple keys as is, otherwise convert string keys to tuple keys
            if isinstance(k, tuple) and len(k) == 2:
                clean_attrs[k] = v
            elif isinstance(k, str):
                clean_attrs[(None, k)] = v

        # Add rel="nofollow" using tuple key
        clean_attrs[(None, "rel")] = "nofollow"
        display_text = attrs.get('_text', '')

        # If trimming is needed, update the '_text' key in attrs directly
        if trim_url_limit is not None and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            trimmed_text = display_text[:trim_url_limit].rstrip() + "..."
            clean_attrs["_text"] = trimmed_text

        return clean_attrs  # always return dict, not tuple!

    return bleach.linkify(text, callbacks=[nofollow])
