import html as htmllib

from bleach import css_sanitizer


class CSSSanitizer(css_sanitizer.CSSSanitizer):
    """Override default `bleach.css_sanitizer.CSSSanitizer` class (mandatory for ByteDeck project)"""

    def sanitize_css(self, style):
        """
        Override `sanitize_css` method, unescape styles before sanitization (fix #1340)
        """
        return super().sanitize_css(htmllib.unescape(style))
