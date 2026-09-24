from django.test import SimpleTestCase

from comments.sanitize import sanitize_comment_html


class SanitizeCommentHTMLTest(SimpleTestCase):
    """Unit tests for the shared comment-HTML sanitizer (issues #1343 / #2113)."""

    def test_sanitize_comment_html__preserves_legitimate_formatting(self):
        """Ordinary formatting tags survive so rich comments render (issue #2113)."""
        html = '<p>hi <b>bold</b> <a href="http://example.com">link</a></p><ul><li>a</li></ul>'
        cleaned = sanitize_comment_html(html)
        self.assertIn('<b>bold</b>', cleaned)
        self.assertIn('<a href="http://example.com">link</a>', cleaned)
        self.assertIn('<li>a</li>', cleaned)

    def test_sanitize_comment_html__strips_script_tag(self):
        """<script> is neutralized so it can't execute (issue #1343)."""
        cleaned = sanitize_comment_html('<script>alert(1)</script>')
        self.assertNotIn('<script>', cleaned)
        self.assertIn('&lt;script&gt;', cleaned)

    def test_sanitize_comment_html__strips_event_handler_attributes(self):
        """Inline event handlers (on*) are removed from otherwise-allowed tags."""
        cleaned = sanitize_comment_html('<img src=x onerror=alert(1)>')
        self.assertNotIn('onerror', cleaned)
        self.assertIn('<img', cleaned)  # the tag itself is allowed, only the handler is dropped

    def test_sanitize_comment_html__strips_denylisted_attributes(self):
        """Explicitly denied attributes (e.g. srcdoc) are stripped even on allowed tags."""
        cleaned = sanitize_comment_html('<iframe srcdoc="<script>alert(1)</script>"></iframe>')
        self.assertNotIn('srcdoc', cleaned)

    def test_sanitize_comment_html__strips_javascript_url(self):
        """javascript: URLs are removed from links."""
        cleaned = sanitize_comment_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn('javascript:', cleaned)

    def test_sanitize_comment_html__none_and_empty_are_safe(self):
        """None / empty input sanitize to an empty string without error."""
        self.assertEqual(sanitize_comment_html(None), '')
        self.assertEqual(sanitize_comment_html(''), '')


class SanitizeCommentHTMLKatexTest(SimpleTestCase):
    """Maths inserted with the editor's Insert Math button survives a comment (issue #2763).

    The Summernote math plugin renders the LaTeX with KaTeX when it is inserted and stores
    the rendered HTML, so what reaches the sanitizer is KaTeX's own markup rather than the
    LaTeX source. These are real fragments of it: a fraction, a square root (the case that
    needs SVG) and a matrix (the case with tall delimiters).
    """

    FRACTION = (
        '<span class="katex"><span class="katex-mathml">'
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow><mfrac>'
        '<mi>a</mi><mi>b</mi></mfrac></mrow>'
        '<annotation encoding="application/x-tex">\\frac{a}{b}</annotation></semantics></math></span>'
        '<span class="katex-html" aria-hidden="true"><span class="base">'
        '<span class="strut" style="height:2.0074em;vertical-align:-0.686em;"></span>'
        '<span class="mord"><span class="mopen nulldelimiter"></span>'
        '<span class="mfrac"><span class="vlist-t vlist-t2"><span class="vlist-r">'
        '<span class="vlist" style="height:1.3214em;">'
        '<span style="top:-2.314em;"><span class="pstrut" style="height:3em;"></span>'
        '<span class="mord"><span class="mord mathnormal">b</span></span></span>'
        '<span style="top:-3.23em;"><span class="pstrut" style="height:3em;"></span>'
        '<span class="frac-line" style="border-bottom-width:0.04em;"></span></span>'
        '</span></span></span></span></span></span></span>'
    )

    SQUARE_ROOT_SVG = (
        '<span class="hide-tail" style="min-width:0.853em;height:1.08em;">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="400em" height="1.08em" '
        'viewBox="0 0 400000 1080" preserveAspectRatio="xMinYMin slice">'
        '<path d="M95,702c-2.7,0,-7.17,-2.7,-13.5,-8c-5.8,-5.3,-9.5,-10,-9.5,-14"></path>'
        '</svg></span>'
    )

    MATRIX_DELIMITER = (
        '<span class="delimsizing mult"><span class="vlist-t vlist-t2">'
        '<span class="vlist" style="height:1.6em;"><span style="top:-1.6em;">'
        '<span class="pstrut" style="height:3.15em;"></span>'
        '<span class="delimsizinginner delim-size1">⎝</span></span></span></span></span>'
    )

    def test_sanitize_comment_html__keeps_the_svg_katex_draws_a_radical_with(self):
        """The svg and path a square root's radical is drawn with survive.

        Neither was in the allow-list, so a square root in a comment came through with its
        contents but no radical over them.
        """
        cleaned = sanitize_comment_html(self.SQUARE_ROOT_SVG)

        self.assertIn('<svg', cleaned)
        self.assertIn('<path', cleaned)
        # SVG attribute names are case sensitive, so these have to come back as they went in
        # or the drawing does not scale to what it covers.
        self.assertIn('viewBox="0 0 400000 1080"', cleaned)
        self.assertIn('preserveAspectRatio="xMinYMin slice"', cleaned)

    def test_sanitize_comment_html__keeps_the_css_katex_stacks_an_expression_with(self):
        """The per-element offsets and rule widths that stack a fraction survive.

        KaTeX works these out from the maths and writes them inline, so they cannot come
        from the stylesheet. Without them every part of the expression sits on one baseline.
        """
        cleaned = sanitize_comment_html(self.FRACTION)

        self.assertIn('vertical-align:-0.686em', cleaned)
        self.assertIn('top:-2.314em', cleaned)
        self.assertIn('border-bottom-width:0.04em', cleaned)

    def test_sanitize_comment_html__keeps_a_tall_delimiter_around_a_matrix(self):
        """A matrix's stretched bracket keeps the offsets that position its pieces."""
        cleaned = sanitize_comment_html(self.MATRIX_DELIMITER)

        self.assertIn('height:1.6em', cleaned)
        self.assertIn('top:-1.6em', cleaned)
        self.assertIn('height:3.15em', cleaned)

    def test_sanitize_comment_html__keeps_position_relative(self):
        """position: relative survives, which is the only position KaTeX asks for."""
        cleaned = sanitize_comment_html('<span style="position:relative;top:-3em;">x</span>')

        self.assertIn('position:relative', cleaned)
        self.assertIn('top:-3em', cleaned)

    def test_sanitize_comment_html__strips_position_that_covers_the_page(self):
        """A comment cannot pin an element over the page to cover what a reader clicks.

        position had to be allowed for KaTeX, and at fixed or absolute it takes an element
        out of the flow, so the value is checked rather than the property alone.
        """
        for value in ('fixed', 'absolute', 'sticky'):
            with self.subTest(value=value):
                cleaned = sanitize_comment_html(
                    f'<span style="position:{value};top:0;left:0;width:100%;height:100%;'
                    'background-color:red;">gotcha</span>'
                )
                self.assertNotIn('position', cleaned)
                # the harmless half of the same style is left alone
                self.assertIn('background-color', cleaned)

    def test_sanitize_comment_html__still_neutralizes_what_svg_can_carry_script_in(self):
        """Allowing svg does not allow the elements SVG can carry script in.

        Those are not in the allow-list, so they come back escaped: text in the page rather
        than elements the browser runs, which is how this sanitizer handles <script> already.
        """
        cleaned = sanitize_comment_html(
            '<svg><script>alert(1)</script><animate onbegin="alert(1)"></animate>'
            '<foreignObject><iframe src="javascript:alert(1)"></iframe></foreignObject></svg>'
        )

        # No element of any of these survives: each is escaped into its own text.
        self.assertNotIn('<script', cleaned)
        self.assertNotIn('<animate', cleaned)
        self.assertNotIn('<foreignObject', cleaned)
        self.assertIn('&lt;script&gt;', cleaned)
        self.assertIn('&lt;animate onbegin="alert(1)"&gt;', cleaned)
        self.assertIn('&lt;foreignObject&gt;', cleaned)
        # An iframe is allowed in a comment on its own account, but not one that loads script.
        self.assertNotIn('javascript:', cleaned)

    def test_sanitize_comment_html__keeps_table_headers_and_captions(self):
        """<th> and <caption> survive a comment.

        A missing comma in the allow-list ran the two entries together into one "thcaption",
        so a table pasted into a comment lost its header row.
        """
        cleaned = sanitize_comment_html(
            '<table><caption>Results</caption><tr><th>Trial</th><td>1</td></tr></table>'
        )

        self.assertIn('<caption>Results</caption>', cleaned)
        self.assertIn('<th>Trial</th>', cleaned)
