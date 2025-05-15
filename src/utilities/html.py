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


def urlize(text):
    """
    Converts plain text URLs into HTML anchor tags using bleach.linkify.
    Adds rel="nofollow" attribute to anchor tags while correctly handling
    attribute keys as tuples to avoid serializer errors.
    """
    if not text:
        return ""

    def nofollow(attrs, new):
        # Create a new dict with all attributes using tuple keys (namespace, attr_name)
        clean_attrs = {}

        for k, v in attrs.items():
            if k == '_text':
                continue
            # Only accept keys that are tuples or strings, but convert string keys to tuple form
            if isinstance(k, tuple) and len(k) == 2:
                clean_attrs[k] = v
            elif isinstance(k, str):
                clean_attrs[(None, k)] = v

        # Add rel="nofollow" using tuple key
        clean_attrs[(None, "rel")] = "nofollow"
        return clean_attrs

    return bleach.linkify(text, callbacks=[nofollow])
