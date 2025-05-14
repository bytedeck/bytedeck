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
    Convert URLs in the given text into clickable HTML links, using bleach.linkify
    for safe HTML escaping and sanitization.

    Args:
        text (str): The input text containing URLs to convert.
        trim_url_limit (int, optional): Maximum length of the displayed URL text.
            If the URL is longer, it will be truncated with '...'.
            The href attribute will always contain the full URL.
            Defaults to None (no trimming).

    Returns:
        str: The text with URLs replaced by safe HTML anchor tags including
             rel="nofollow".
    """

    def shorten_url(attrs, new=False):
        """
        Modify the link attributes to optionally trim the displayed URL text.

        Args:
            attrs (dict): Dictionary of link attributes (e.g., 'href', 'title').
            new (bool): Whether this is a newly created link (unused).

        Returns:
            dict: Modified attributes with possibly trimmed '_text' for display.
        """
        href = attrs.get("href", "")
        if trim_url_limit and len(href) > trim_url_limit:
            display = href[:trim_url_limit].rstrip() + "..."
            attrs["_text"] = display
        return attrs

    def linkify_callback(attrs, new=False):
        """
        Callback function used by bleach.linkify to customize link attributes.

        Adds rel="nofollow" and trims displayed URL text if requested.

        Args:
            attrs (dict): Link attributes.
            new (bool): Whether this is a new link (unused).

        Returns:
            dict: Modified link attributes.
        """
        attrs = shorten_url(attrs, new)
        attrs.setdefault("rel", "nofollow")
        return attrs

    if not text:
        return ""

    return bleach.linkify(text, callbacks=[linkify_callback])
