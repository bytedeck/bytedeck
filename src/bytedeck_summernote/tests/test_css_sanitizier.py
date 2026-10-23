from bleach import clean  # noqa

from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class TestCSSSanitizer(ByteDeckTenantTestCase):
    """ByteDeck's CSSSanitizer implementation, fixes various issues"""

    def test_sanitize_css__preserves_escaped_values(self):
        """The sanitizer should not strip/remove escaped CSS values."""
        from bytedeck_summernote.css_sanitizer import CSSSanitizer
        from bytedeck_summernote.settings import STYLES

        css_sanitizer = CSSSanitizer(allowed_css_properties=STYLES)

        escaped_css_values = """<p>Lorem ipsum<span style="font-family: &quot;Comic Sans MS&quot;;">dolor</span> sit amet</p>"""
        expected = """<p>Lorem ipsum<span style='font-family: "Comic Sans MS";'>dolor</span> sit amet</p>"""

        assert (
            clean(
                escaped_css_values, tags=["p", "span"], attributes={"span": ["style"]}, css_sanitizer=css_sanitizer
            )
            == expected
        )

    def test_sanitize_css__keeps_position_relative(self):
        """position: relative survives, which is the one KaTeX lays an expression out with."""
        from bytedeck_summernote.css_sanitizer import CSSSanitizer
        from bytedeck_summernote.settings import STYLES

        css_sanitizer = CSSSanitizer(allowed_css_properties=STYLES)

        self.assertEqual(css_sanitizer.sanitize_css('position: relative'), 'position: relative;')
        self.assertEqual(css_sanitizer.sanitize_css('position: static'), 'position: static;')

    def test_sanitize_css__drops_position_that_leaves_the_flow(self):
        """fixed, absolute and sticky are dropped: they let an element sit over the page.

        The rest of the declaration is kept, since only this property is at issue.
        """
        from bytedeck_summernote.css_sanitizer import CSSSanitizer
        from bytedeck_summernote.settings import STYLES

        css_sanitizer = CSSSanitizer(allowed_css_properties=STYLES)

        for value in ('fixed', 'absolute', 'sticky', 'FIXED'):
            with self.subTest(value=value):
                cleaned = css_sanitizer.sanitize_css(f'position: {value}; color: red')
                self.assertNotIn('position', cleaned)
                self.assertIn('color: red', cleaned)

    def test_sanitize_css__drops_every_declaration_that_is_not_allowed(self):
        """A style made only of disallowed declarations sanitizes to nothing."""
        from bytedeck_summernote.css_sanitizer import CSSSanitizer
        from bytedeck_summernote.settings import STYLES

        css_sanitizer = CSSSanitizer(allowed_css_properties=STYLES)

        self.assertEqual(css_sanitizer.sanitize_css('position: fixed'), '')
        self.assertEqual(css_sanitizer.sanitize_css('behavior: url(x)'), '')
        self.assertEqual(css_sanitizer.sanitize_css(''), '')
