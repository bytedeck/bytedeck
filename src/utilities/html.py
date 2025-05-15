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
    Convert URLs in the given text into clickable, sanitized anchor tags.
    Optionally trims the displayed URL text and adds rel="nofollow".
    """
    if not text:
        return ""

    def add_nofollow(attrs, new):
        # Just ensure rel="nofollow" is set
        if attrs is None:
            return None
        attrs["rel"] = "nofollow"
        return attrs

    return bleach.linkify(text, callbacks=[add_nofollow])
