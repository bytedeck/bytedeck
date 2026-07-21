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
