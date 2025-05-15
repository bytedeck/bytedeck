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
    Adds rel="nofollow" to anchor tags while handling both namespaced and
    non-namespaced attribute keys.
    """
    if not text:
        return ""

    def nofollow(attrs, new):
        # Create a new dictionary only with valid attribute keys
        clean_attrs = {}
        for k, v in attrs.items():
            # Skip keys like '_text' or any keys that are not tuples or strings representing valid HTML attribute names
            if k == '_text':
                continue

            # Bleach expects attribute keys as tuples (namespace, name)
            # but sometimes strings too, so keep both
            if (isinstance(k, tuple) or isinstance(k, str)) and isinstance(v, str):
                clean_attrs[k] = v

        # Add rel="nofollow" to string key 'rel' (typical usage)
        clean_attrs["rel"] = "nofollow"
        return clean_attrs

    return bleach.linkify(text, callbacks=[nofollow])
