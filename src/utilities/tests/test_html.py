import warnings

from bs4 import MarkupResemblesLocatorWarning
from django.test import SimpleTestCase
from html.parser import HTMLParser
from utilities.html import EMBEDDED_CONTENT_TAGS, in_a_paragraph, is_empty_html, link_embeds, textify, urlize
from comments.models import clean_html


class TestUtilsText(SimpleTestCase):
    """
    Various tests for `utilities.html` module.
    """

    def test_textify__converts_html_to_markdown(self):
        """
        Generate a plain text version of an html content using html2text library.
        """
        html = """<p><strong>Zed's</strong> dead baby, <em>Zed's</em> dead.</p>"""
        output = textify(html)
        self.assertEqual(output, """**Zed's** dead baby, _Zed's_ dead.\n\n""")

    def test_textify__does_not_ignore_links(self):
        """
        Don't ignore links anymore, I like links
        """
        html = """<p>Hello, <a href='https://www.google.com/earth/'>world</a>!</p>"""
        output = textify(html)
        self.assertEqual(output, """Hello, [world](https://www.google.com/earth/)!\n\n""")


class LinkTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.link_texts = []

    def handle_data(self, data):
        self.link_texts.append(data)

    def get_text(self):
        return "".join(self.link_texts)


class UrlizeTests(SimpleTestCase):
    def test_urlize__basic(self):
        """
        Test that a simple URL is correctly converted into an anchor tag
        and the URL text is preserved.

        Tests various scenarios:
        - Plain URL conversion
        - URLs preceded by numeric prefixes (e.g., "1.www.example.com")
        - URLs preceded by alphabetic prefixes (e.g., "a.www.example.com")
        - Both www and http protocol variants

        Verifies that prefixes remain outside the anchor tag href attribute.
        """
        text = "Visit www.example.com"
        result = urlize(text)
        self.assertIn('<a href="http://www.example.com"', result)
        self.assertIn('www.example.com', result)

        text = "1.www.example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('1.<a href="http://www.example.com"'))

        text = "a.www.example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('a.<a href="http://www.example.com"'))

        text = "1.http://example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('1.<a href="http://example.com"'))

        text = "a.http://example.com"
        result = urlize(text)
        self.assertTrue(result.startswith('a.<a href="http://example.com"'))

    def test_urlize__empty_or_none(self):
        """
        Test that empty string or None input returns an empty string without error.

        Parameters tested:
        - Empty string ("")
        - None value

        Expected behavior: Both should return empty string without raising exceptions.
        """
        self.assertEqual(urlize(""), "")
        self.assertEqual(urlize(None), "")

    def test_urlize__trim_url_limit(self):
        """
        Test that long URLs are visually trimmed in the anchor text,
        while the href attribute retains the full URL.

        Test cases:
        - Long URL with custom trim_url_limit
        - Short URL with a large limit (no trimming expected)
        """
        url = "http://example.com/this/is/a/very/long/url/that/needs/trimming"
        trimmed_length = 30
        result = urlize(url, trim_url_limit=trimmed_length)

        expected_display = url[:trimmed_length].rstrip() + "..."

        # Parse visible text
        parser = LinkTextExtractor()
        parser.feed(result)
        visible_text = parser.get_text()

        self.assertTrue(result.startswith(f'<a href="{url}"'))
        self.assertEqual(visible_text, expected_display)

        # Test no trim
        url = "http://short.url"
        result = urlize(url, trim_url_limit=100)
        self.assertIn(url, result)
        self.assertNotIn("...", result)

    def test_urlize__multiple_urls(self):
        """
        Test that multiple URLs in the input text are all converted into anchor tags.

        Input: Text containing two different URLs with different protocols
        Expected: Both URLs should be converted to separate anchor tags
        Verifies: Correct href attributes and proper count of anchor elements
        """
        text = "Links: http://foo.com and https://bar.com/page"
        result = urlize(text)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="https://bar.com/page"', result)
        self.assertEqual(result.count('<a '), 2)

    def test_urlize__url_positions(self):
        """
        Test that URLs are correctly linkified regardless of their position
        in the input string (start, middle, or end).

        Test cases:
        - URL at the beginning of the string
        - URL in the middle with surrounding text
        - URL at the end of the string

        Verifies: Proper href attribute generation for all positions
        """
        self.assertIn('<a href="http://start.com"', urlize("http://start.com is at the start"))
        self.assertIn('<a href="http://middle.com"', urlize("Text before http://middle.com text after"))
        self.assertIn('<a href="http://end.com"', urlize("Ends with http://end.com"))

    def test_urlize__non_url_text(self):
        """
        Test that plain text without any URLs is returned unmodified.
        """
        text = "This is just a sentence. Not a link!"
        result = urlize(text)
        self.assertEqual(result, text)

    def test_urlize__trailing_punctuation(self):
        """
        Test that trailing punctuation such as periods is excluded
        from the anchor tag.

        Input: "Visit http://example.com."
        Expected: Anchor ends before period, period remains outside
        """
        result = urlize("Visit http://example.com.")
        self.assertIn('href="http://example.com"', result)
        self.assertTrue(result.endswith("</a>."))

    def test_urlize__already_linked_html(self):
        """
        Test that pre-existing <a> tags are preserved and not double-processed.

        Security consideration: Prevents nested anchor tags which would create
        invalid HTML and potential security vulnerabilities.

        Input: HTML string containing existing anchor tag
        Expected: Original HTML returned unchanged
        """
        html = '<a href="http://example.com">example</a>'
        result = urlize(html)
        self.assertEqual(result, html)

    def test_urlize__no_javascript_links(self):
        """
        Test that javascript: links are not linkified for security reasons.
        """
        text = "Click javascript:alert('xss')"
        result = urlize(text)
        self.assertNotIn("href=", result)  # Should not linkify

    def test_clean_html__urlize_integration(self):
        """
        Ensure that clean_html applies urlize logic to plain text URLs.
        """
        text = "Go to www.example.com"
        result = clean_html(text)
        self.assertIn('<a href="http://www.example.com"', result)
        self.assertIn('target="_blank"', result)

    def test_clean_html__trims_long_urls(self):
        """
        Test that clean_html trims long URLs in display text.
        """
        url = "http://example.com/this/is/a/very/long/path/that/needs/to/be/trimmed"
        result = clean_html(url)
        self.assertIn("...", result)
        self.assertIn('href="http://example.com/this/is/a/very/long/path/that/needs/to/be/trimmed"', result)

    def test_clean_html__ignores_existing_links(self):
        """
        Test that clean_html doesn't re-process existing anchor tags.
        """
        html = '<a href="http://example.com">Click</a>'
        result = clean_html(html)
        self.assertEqual(result.count('<a '), 1)
        self.assertIn('href="http://example.com"', result)
        self.assertIn('target="_blank"', result)

    def test_clean_html__a_comment_that_is_only_a_link_raises_no_warning(self):
        """A comment that is nothing but a link is cleaned without bs4's "looks like a URL" warning (#1280).

        bs4 warns when the markup it is given looks more like a location than HTML. A student
        handing in a Google Doc writes exactly that, so the approvals page logged the warning for
        their comments. The "always" filter is appended, so it shows any warning nothing earlier
        in the filter list silences, which is where the app's own filter sits.
        """
        link = "https://docs.google.com/document/d/abc123/edit"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", append=True)
            result = clean_html(link)

        self.assertEqual([w.message for w in caught if issubclass(w.category, MarkupResemblesLocatorWarning)], [])
        self.assertIn(f'href="{link}"', result)

    def test_clean_html__makes_no_deprecated_bs4_call(self):
        """clean_html uses none of the bs4 spellings deprecated since 4.0 (#1280).

        `find_all(text=...)`, `renderContents()`, `findAll()` and `findPrevious()` each warn on
        every call. The input reaches every step: a link to urlize and a bare <li> to wrap.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            result = clean_html("<ul><li>one</li></ul><li>two</li> see www.example.com")

        self.assertIn('href="http://www.example.com"', result)

    def test_clean_html__an_empty_comment_logs_nothing(self):
        """An empty comment, as every new draft is, is cleaned without a decoding warning in the log (#1280)."""
        with self.assertNoLogs("bs4.dammit", level="WARNING"):
            self.assertEqual(clean_html(""), "")

    def test_clean_html__multiple_urls(self):
        """
        Ensure that multiple unformatted URLs are handled correctly.
        """
        html = "http://foo.com and www.bar.com"
        result = clean_html(html)
        self.assertIn('href="http://foo.com"', result)
        self.assertIn('href="http://www.bar.com"', result)
        self.assertEqual(result.count("<a "), 2)

    def test_clean_html__does_not_link_javascript(self):
        """
        Ensure javascript: links are not linkified.
        """
        text = "Check javascript:alert('XSS')"
        result = clean_html(text)
        self.assertNotIn('<a ', result)

    def test_urlize__numbered_list_with_br(self):
        """Numbered list items separated by <br> are linkified with prefixes kept outside the anchors."""
        # Input simulating comment input with <br> instead of newlines
        input_text = (
            "1.www.testing.com<br>"
            "2.www.example.com<br>"
            "3.www.notarealsite.com<br>"
            "4.testing.com<br>"
            "5.example.com"
        )

        result = urlize(input_text)

        # Make sure each prefix is outside the <a> tag
        self.assertTrue(result.startswith('1.<a href="http://www.testing.com"'))
        self.assertIn('2.<a href="http://www.example.com"', result)
        self.assertIn('3.<a href="http://www.notarealsite.com"', result)
        self.assertIn('4.<a href="http://testing.com"', result)
        self.assertIn('5.<a href="http://example.com"', result)

        # Ensure prefixes are NOT inside the links
        self.assertNotIn('<a href="http://1.', result)
        self.assertNotIn('<a href="http://2.', result)


class IsEmptyHtmlTests(SimpleTestCase):
    """Tests for `utilities.html.is_empty_html`, the "would this render as nothing?" test."""

    def test_is_empty_html__nothing_at_all(self):
        """A missing or empty value is empty, so callers need no None check of their own."""
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertTrue(is_empty_html(value))

    def test_is_empty_html__untouched_summernote_editor(self):
        """The markup an editor posts when the user typed nothing is empty (#2560).

        These are the payloads a student actually produces: clicking into the editor and
        leaving gives `<p><br></p>`, typing a space gives `<p>&nbsp;</p>`, and pressing enter
        a few times gives a run of empty paragraphs. None of them are an answer.
        """
        for value in ("<p><br></p>", "<p></p>", "<p> </p>", "<p>&nbsp;</p>", "<p><br></p><p><br></p>", "<br>"):
            with self.subTest(value=value):
                self.assertTrue(is_empty_html(value))

    def test_is_empty_html__real_text(self):
        """Text a user typed is content, however it is wrapped or formatted."""
        for value in ("hello", "<p>hello</p>", "<p><strong>hi</strong></p>", "<ul><li>one</li></ul>", "<p>0</p>"):
            with self.subTest(value=value):
                self.assertFalse(is_empty_html(value))

    def test_is_empty_html__entity_that_is_not_whitespace(self):
        """An entity is judged by the character it renders as, not by the text spelling it.

        `&amp;` decodes to a visible "&", unlike `&nbsp;`, so a value made only of it is
        content. Decoding before the whitespace test is what tells the two apart.
        """
        self.assertFalse(is_empty_html("<p>&amp;</p>"))

    def test_is_empty_html__embedded_content_without_text(self):
        """A picture or an embed is an answer even though stripping tags leaves nothing.

        A student answering "show me your work" by pasting a screenshot, or by embedding a
        video, has answered. Every tag in `EMBEDDED_CONTENT_TAGS` is treated this way.
        """
        for tag in EMBEDDED_CONTENT_TAGS:
            with self.subTest(tag=tag):
                self.assertFalse(is_empty_html(f"<p><{tag} src='x'></{tag}></p>"))

    def test_is_empty_html__embed_tag_is_matched_however_it_is_written(self):
        """Whitespace and capitals inside a tag don't hide it from the content check."""
        for value in ("<P><  IMG SRC='x'></P>", "<p><Iframe src='x'></Iframe></p>"):
            with self.subTest(value=value):
                self.assertFalse(is_empty_html(value))

    def test_is_empty_html__typed_tag_name_is_not_an_embed(self):
        """An escaped tag the user typed about is text, not embedded content.

        A student answering "which tag embeds a picture?" with `<img>` posts `&lt;img&gt;`
        from a rich-text editor. That is a real answer, and it must be counted as one for
        its text rather than mistaken for an actual picture.
        """
        self.assertFalse(is_empty_html("<p>&lt;img&gt;</p>"))


class InAParagraphTests(SimpleTestCase):
    """Tests for `utilities.html.in_a_paragraph`, which lays a fragment out in blocks without
    nesting a paragraph inside another (#2713)."""

    def test_in_a_paragraph__wraps_bare_text(self):
        """Text with no markup of its own, as a plain textarea posts it, becomes a paragraph."""
        self.assertEqual(in_a_paragraph("done"), "<p>done</p>")

    def test_in_a_paragraph__wraps_text_with_only_inline_tags(self):
        """Bold text and links sit inside a paragraph rather than making one."""
        fragment = 'a <b>bold</b> <a href="https://example.org">link</a>'
        self.assertEqual(in_a_paragraph(fragment), f"<p>{fragment}</p>")

    def test_in_a_paragraph__leaves_the_editors_paragraphs_as_they_are(self):
        """The editor lays its text out in paragraphs already, so they are not put inside another."""
        fragment = "<p>one</p><p>two</p>"
        self.assertEqual(in_a_paragraph(fragment), fragment)

    def test_in_a_paragraph__leaves_other_blocks_as_they_are(self):
        """A list, a heading or a quote is a block of its own too."""
        for fragment in ("<ul><li>x</li></ul>", "<h3>Title</h3>", "<blockquote>q</blockquote>", "<OL><li>x</li></OL>"):
            with self.subTest(fragment=fragment):
                self.assertEqual(in_a_paragraph(fragment), fragment)

    def test_in_a_paragraph__a_typed_tag_is_text(self):
        """An escaped tag the user typed about is text, so it still gets its paragraph."""
        self.assertEqual(in_a_paragraph("&lt;p&gt; makes a paragraph"), "<p>&lt;p&gt; makes a paragraph</p>")


class LinkEmbedsTests(SimpleTestCase):
    """Tests for `utilities.html.link_embeds`, which puts a link where an email can't show what
    is embedded (#1249)."""

    def test_link_embeds__a_youtube_player_links_to_its_watch_page(self):
        """The editor's YouTube player becomes a link to the video's own page, in its place."""
        html = (
            '<p><iframe frameborder="0" src="//www.youtube.com/embed/1DKm96Ftfko?rel=0" width="640" height="360" '
            'class="note-video-clip"></iframe></p>'
        )
        self.assertEqual(
            link_embeds(html),
            '<p><span>Watch the video: <a href="https://www.youtube.com/watch?v=1DKm96Ftfko">'
            'https://www.youtube.com/watch?v=1DKm96Ftfko</a></span></p>',
        )

    def test_link_embeds__a_youtube_player_keeps_its_start_time(self):
        """A YouTube player set to start part-way through (the editor's Embed Video start time)
        links to its watch page at that time."""
        html = '<iframe src="//www.youtube.com/embed/1DKm96Ftfko?rel=0&amp;start=90&amp;end=120&amp;enablejsapi=1"></iframe>'
        self.assertIn('<a href="https://www.youtube.com/watch?v=1DKm96Ftfko&amp;t=90s">', link_embeds(html))

    def test_link_embeds__an_unusable_start_time_is_left_out(self):
        """A start time that isn't a plain number of seconds is left out of the link, rather than
        stopping the email: more digits than int() takes from a string, a character that only
        looks like a digit, or zero."""
        for start in ("9" * 5000, "\u00b2", "0"):
            with self.subTest(start=start[:10]):
                html = f'<iframe src="//www.youtube.com/embed/1DKm96Ftfko?start={start}"></iframe>'
                self.assertIn('<a href="https://www.youtube.com/watch?v=1DKm96Ftfko">', link_embeds(html))

    def test_link_embeds__a_vimeo_player_links_to_its_page(self):
        """A Vimeo player links to the video's page on vimeo.com."""
        html = '<p><iframe src="//player.vimeo.com/video/76979871" class="note-video-clip"></iframe></p>'
        self.assertIn('Watch the video: <a href="https://vimeo.com/76979871">https://vimeo.com/76979871</a>', link_embeds(html))

    def test_link_embeds__a_video_file_links_to_the_file(self):
        """A <video> links to its file, from its own address or its first source. An address on
        the deck itself is made whole with the deck's root URL, so it opens from an inbox."""
        self.assertIn(
            'Watch the video: <a href="https://deck.example.com/media/clip.mp4">',
            link_embeds('<video controls src="/media/clip.mp4"></video>', 'https://deck.example.com'),
        )
        self.assertIn(
            'Watch the video: <a href="https://cdn.example.com/clip.webm">',
            link_embeds('<video controls><source src="https://cdn.example.com/clip.webm" type="video/webm"></video>'),
        )

    def test_link_embeds__another_embedded_page_links_to_its_address(self):
        """An embed that isn't a video player, such as a slide deck, links to its own address."""
        self.assertEqual(
            link_embeds('<iframe src="https://docs.google.com/presentation/d/abc/embed"></iframe>'),
            '<span>Open the embedded page: <a href="https://docs.google.com/presentation/d/abc/embed">'
            'https://docs.google.com/presentation/d/abc/embed</a></span>',
        )

    def test_link_embeds__html_without_embeds_is_left_as_written(self):
        """HTML with nothing embedded comes back exactly as it went in."""
        for html in ('<p>Hello<br>there</p>', '', None):
            with self.subTest(html=html):
                self.assertEqual(link_embeds(html), html)

    def test_link_embeds__an_embed_without_a_web_address_is_left_alone(self):
        """No link is made where there's no web page to open: an embed with no address, one
        that runs script, or one on the deck itself when the deck's address isn't known."""
        for html in (
            '<iframe></iframe>', '<iframe src="javascript:alert(1)"></iframe>', '<video></video>',
            '<video src="/media/clip.mp4"></video>',
        ):
            with self.subTest(html=html):
                self.assertEqual(link_embeds(html), html)
