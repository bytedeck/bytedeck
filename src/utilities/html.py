"""
HTML utilities suitable for global use, matching `django.utils.html` naming convention.
"""
# html2text is a python script that converts a page of HTML into clean, easy-to-read plain ASCII text
import html2text
import bleach


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
    attribute keys as tuples to avoid serializer errors.
    """
    if not text:
        return ""

    def nofollow(attrs, new):
        clean_attrs = {}

        for k, v in attrs.items():
            if k == '_text':
                continue
            if isinstance(k, tuple) and len(k) == 2:
                clean_attrs[k] = v
            elif isinstance(k, str):
                clean_attrs[(None, k)] = v

        # Add rel="nofollow"
        clean_attrs[(None, "rel")] = "nofollow"

        # Apply trimming to the displayed text (not href)
        display_text = attrs.get('_text', '')
        if trim_url_limit is not None and isinstance(display_text, str):
            if len(display_text) > trim_url_limit:
                trimmed = display_text[:trim_url_limit].rstrip() + "..."
                clean_attrs[(None, '_text')] = trimmed
            else:
                clean_attrs[(None, '_text')] = display_text
        else:
            clean_attrs[(None, '_text')] = display_text

        return clean_attrs

    return bleach.linkify(text, callbacks=[nofollow])
