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
    Converts plain text URLs into links using bleach.
    Safely adds rel="nofollow" without changing link text.
    """
    if not text:
        return ""

    def nofollow(attrs, new):
        print("🔍 CALLBACK CALLED WITH attrs =", attrs)
        if not isinstance(attrs, dict):
            print("❌ attrs is not a dict!")
            return None

        clean_attrs = {}
        for k, v in attrs.items():
            print("   ➤ Key:", k, "Type:", type(k), "| Value:", v, "Type:", type(v))
            if isinstance(k, str) and isinstance(v, str):
                clean_attrs[k] = v
        clean_attrs["rel"] = "nofollow"
        print("✅ Returning clean_attrs:", clean_attrs)
        return clean_attrs

    return bleach.linkify(text, callbacks=[nofollow])
