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
    if not text:
        return ""

    def nofollow(attrs, new):
        print(f"nofollow called with attrs={attrs}, new={new}, trim_url_limit={trim_url_limit}")
        clean_attrs = {}
        for k, v in attrs.items():
            if k == '_text':
                continue
            if isinstance(k, tuple) and len(k) == 2:
                clean_attrs[k] = v
            elif isinstance(k, str):
                clean_attrs[(None, k)] = v
        clean_attrs[(None, "rel")] = "nofollow"
        display_text = attrs.get('_text', '')

        if trim_url_limit is not None and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            trimmed_text = display_text[:trim_url_limit].rstrip() + "..."
            print("Returning:", clean_attrs, trimmed_text)
            return clean_attrs, trimmed_text
        else:
            print("Returning:", clean_attrs, display_text)
            return clean_attrs, display_text

    return bleach.linkify(text, callbacks=[nofollow])
