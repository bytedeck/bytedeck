"""
HTML utilities suitable for global use, matching `django.utils.html` naming convention.
"""
# html2text is a python script that converts a page of HTML into clean, easy-to-read plain ASCII text
import html2text
import bleach
import html as html_module
import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from django.utils.html import strip_tags

# Tags that are content in their own right, with no text of their own. A student can answer a
# question with nothing but a pasted screenshot or an embedded video, so `is_empty_html` has to
# see those as an answer even though stripping the tags leaves an empty string behind.
EMBEDDED_CONTENT_TAGS = frozenset({
    "img", "iframe", "video", "audio", "source", "track", "embed", "object", "svg", "canvas", "math",
})

# Tags that make a block of their own, which a paragraph cannot hold. A fragment with any of these
# in it is already laid out in blocks, so `in_a_paragraph` leaves it as it is.
BLOCK_TAGS = frozenset({
    "p", "div", "ul", "ol", "li", "dl", "dt", "dd", "table", "caption", "thead", "tbody", "tfoot",
    "tr", "th", "td", "blockquote", "pre", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "figure",
    "figcaption", "section", "article", "aside", "header", "footer", "nav", "main", "address",
    "details", "summary", "fieldset", "form",
})

# The name of each opening tag in a fragment, e.g. "<p><img src='x'>" -> ["p", "img"]. Only text
# outside a tag can be escaped, so an `&lt;img&gt;` the user typed is never matched here.
_OPENING_TAG_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9:-]*)")


def in_a_paragraph(fragment):
    """The fragment laid out in blocks: in a paragraph of its own when it is only text and inline
    tags, and as it is when it already has blocks.

    The Summernote editor lays a comment out in paragraphs and lists itself, while a plain
    textarea, or text the app writes, is bare. Putting the editor's markup inside another
    paragraph nests a paragraph or a list inside one, which HTML does not allow: a browser closes
    the outer paragraph early and leaves a stray end tag behind (#2713).

    Args:
        fragment (str): the HTML fragment, e.g. "done" or "<p>done</p>".

    Returns:
        str: e.g. "<p>done</p>" for both of those.
    """
    tags = {name.lower() for name in _OPENING_TAG_RE.findall(fragment)}
    return fragment if tags & BLOCK_TAGS else f"<p>{fragment}</p>"


def is_empty_html(value):
    """Whether a fragment of user-authored HTML holds nothing a reader would see.

    The Summernote editor never submits an empty string: an editor a student clicked into and
    left alone posts ``<p><br></p>``, and one they typed a space into posts ``<p>&nbsp;</p>``.
    Both are truthy, so a plain ``if not value`` check reads them as content and lets a blank
    answer through a required field (#2560). Tags and entities are removed and the remainder
    tested for any non-whitespace character (``&nbsp;`` decodes to ``\xa0``, which ``strip()``
    counts as whitespace).

    The question asked is deliberately "is this definitely empty?", not "is this content?".
    Anything uncertain is reported as non-empty, because refusing an answer a student really
    gave is far worse than accepting a blank one: hence `EMBEDDED_CONTENT_TAGS`, which answers
    False for a fragment whose whole content is a picture or an embed.

    Args:
        value: HTML from a rich-text editor, or None/empty for a field never filled in.

    Returns:
        bool: True when the fragment would render as nothing.
    """
    if not value:
        return True

    text = str(value)

    tags = {name.lower() for name in _OPENING_TAG_RE.findall(text)}
    if tags & EMBEDDED_CONTENT_TAGS:
        return False

    # unescape after stripping, so an entity standing alone ("&nbsp;") is judged as the
    # character it renders as rather than as the seven literal characters that spell it
    return not html_module.unescape(strip_tags(text)).strip()


def textify(html):
    """
    Generate a plain text version of an html content using html2text library.
    """
    h = html2text.HTML2Text()
    # don't ignore links anymore, I like links
    h.ignore_links = False
    return h.handle(html)


# The page a video player's address stands for, for the players the editor embeds, so a link
# opens the video's own page rather than a bare player: (pattern for the player's address, with
# the video's id as its group; the video's page, formatted with that id; how the page is told to
# start part-way through, formatted with the seconds the player starts at, or None when the
# editor gives the player no start time).
_VIDEO_PAGES = (
    (
        re.compile(r"^https?://(?:www\.)?youtube(?:-nocookie)?\.com/embed/([\w-]+)"),
        "https://www.youtube.com/watch?v={}", "&t={}s",
    ),
    (re.compile(r"^https?://player\.vimeo\.com/video/(\d+)"), "https://vimeo.com/{}", None),
    (re.compile(r"^https?://(?:www\.)?dailymotion\.com/embed/video/(\w+)"), "https://www.dailymotion.com/video/{}", None),
)

# an opening <iframe> or <video> tag, however it's written
_EMBED_TAG_RE = re.compile(r"<\s*(?:iframe|video)\b", re.IGNORECASE)

# a player's start time: whole seconds in plain digits, up to 999999 (over 277 hours)
_START_SECONDS_RE = re.compile(r"[0-9]{1,6}")


def link_embeds(html, root_url=""):
    """Put a link in place of each video or page embedded in a fragment of HTML.

    An email client shows no embedded player: it drops an <iframe>, and few play a <video>. So a
    video in an announcement left nothing behind in its email (#1249). Each one becomes a line
    linking to it: "Watch the video:" and the video's own page for a YouTube, Vimeo or Dailymotion
    player (from the time a YouTube player was set to start at), its file for a <video>, and
    "Open the embedded page:" and its address for anything else embedded, such as a slide deck. The line is inline, as the embed was, since the editor
    puts an embed inside a paragraph.

    An embed is left as it is when there's no web page to send a reader to: no address, one that
    isn't http(s), or one on the deck itself when `root_url` isn't given.

    Args:
        html (str or None): a fragment of HTML, such as an announcement's content.
        root_url (str): the deck's root URL, which makes an address on the deck itself
            (/media/...) one that opens from an inbox.

    Returns:
        str or None: the fragment with each embed replaced, or exactly as it was when nothing
        is embedded in it.
    """
    if not html or not _EMBED_TAG_RE.search(html):
        return html  # nothing embedded, so the HTML goes out exactly as written

    soup = BeautifulSoup(html, "html.parser")
    for embed in soup.find_all(["iframe", "video"]):
        source = embed.find("source", src=True) if embed.name == "video" else None
        address = (embed.get("src") or (source["src"] if source else "")).strip()
        if address.startswith("//"):
            address = f"https:{address}"  # the editor writes a player's address without its scheme
        elif address.startswith("/"):
            address = f"{root_url.rstrip('/')}{address}" if root_url else ""
        if not address.lower().startswith(("http://", "https://")):
            continue

        label = "Watch the video" if embed.name == "video" else "Open the embedded page"
        for player, page, start_at in _VIDEO_PAGES:
            match = player.match(address)
            if match:
                # the start time the editor's Embed Video dialog gives a YouTube player, in whole
                # seconds; anything else (more digits than a video runs to, or a character that
                # only looks like a digit) is left out of the link
                start = parse_qs(urlsplit(address).query).get("start", [""])[0]
                page = page.format(match.group(1))
                if start_at and _START_SECONDS_RE.fullmatch(start) and int(start):
                    page += start_at.format(int(start))
                address, label = page, "Watch the video"
                break

        line = soup.new_tag("span")
        line.append(f"{label}: ")
        link = soup.new_tag("a", href=address)
        link.string = address
        line.append(link)
        embed.replace_with(line)
    return str(soup)


# Regular expression to match list prefixes like "1." or "a."
# This checks if the line starts with a number or a single letter followed by a dot,
# and makes sure it is immediately followed by a non-space character.
# For example, it matches "1.example.com" or "a.example.com" but not "1. example.com".
# https://regex101.com/r/402DAE/1
LIST_PREFIX_RE = re.compile(r'^([0-9]+|[a-zA-Z])\.(?=\S)')


def urlize(text, trim_url_limit=None):
    """
    Linkify URLs in text while preserving list prefixes and working with <br>-separated HTML.

    - Preserves numeric or alphabetic list prefixes (e.g. "1.", "a.") outside of links.
    - Handles input text where newlines have been replaced by <br> tags.
    - Skips linkifying if the input already contains HTML links.
    - Optionally trims the display text of links longer than `trim_url_limit`.

    Args:
        text (str): The input text or HTML to linkify.
        trim_url_limit (int, optional): Maximum length for visible URL text, truncates if exceeded.

    Returns:
        str: Text with URLs converted to HTML anchor tags, preserving prefixes.
    """

    if not text:
        return ""

    # Skip processing if text already contains an HTML anchor tag,
    # to avoid double-linking or corrupting existing links.
    if re.search(r'<a\s+[^>]*href=', text, re.IGNORECASE):
        return text

    def trim(attrs, new):
        """
        bleach.linkify callback to optionally trim visible URL text.

        Preserves all anchor tag attributes except '_text' which is trimmed
        and appended with "..." if it exceeds the trim_url_limit.

        Args:
            attrs (dict): Attributes of the anchor tag, including '_text' as display text.
            new (bool): Indicates if the link is newly created (unused here).

        Returns:
            dict: Modified attributes with trimmed '_text' if necessary.
        """
        # Keep all attributes except '_text' unchanged
        clean_attrs = {
            (None, k) if isinstance(k, str) else k: v
            for k, v in attrs.items() if k != '_text'
        }
        display_text = attrs.get("_text", "")
        if trim_url_limit and isinstance(display_text, str) and len(display_text) > trim_url_limit:
            # Trim and append ellipsis if display text is too long
            display_text = display_text[:trim_url_limit] + "..."
        clean_attrs["_text"] = display_text
        return clean_attrs

    # Split input text by <br> tags, which represent line breaks after cleaning.
    parts = text.split('<br>')
    processed_parts = []

    # Process each line separately to detect and preserve list prefixes
    for part in parts:
        match = LIST_PREFIX_RE.match(part)
        prefix = match.group(0) if match else ''  # Extract prefix like "1." or "a.", if present
        rest = part[len(prefix):] if match else part  # The rest of the line after the prefix
        # Linkify the remainder, then prepend the prefix (if any)
        processed = prefix + bleach.linkify(rest, callbacks=[trim])
        processed_parts.append(processed)

    # Rejoin lines with <br> to preserve original formatting
    return '<br>'.join(processed_parts)
