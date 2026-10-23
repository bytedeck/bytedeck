import html as htmllib

import tinycss2

from bleach import css_sanitizer

# Properties that are only safe at some of their values, as {property: {allowed values}}.
#
# bleach decides per property, not per value, so a property is otherwise all or nothing.
# "position" has to be allowed for KaTeX to lay an expression out (#2763), but at "fixed"
# or "absolute" it takes an element out of the flow and lets it sit anywhere on the page,
# including over a control the reader meant to click. Comment HTML is written by students
# and rendered with |safe, so that is a real thing to hand out. KaTeX only ever asks for
# "relative", and "static" is the default, so neither buys an author anything.
VALUE_ALLOW_LIST = {
    "position": {"relative", "static"},
}


class CSSSanitizer(css_sanitizer.CSSSanitizer):
    """Override default `bleach.css_sanitizer.CSSSanitizer` class (mandatory for ByteDeck project)"""

    def sanitize_css(self, style):
        """Return ``style`` with the declarations that are not allowed removed.

        Unescapes first, so a style that arrived HTML-escaped is read as the CSS it is
        (fix #1340), then drops any declaration whose property is restricted to particular
        values and does not have one of them (see VALUE_ALLOW_LIST).

        Args:
            style (str): the value of a style attribute, as it was written.

        Returns:
            str: the declarations that survived, or '' when none did.
        """
        sanitized = super().sanitize_css(htmllib.unescape(style))
        if not sanitized:
            return sanitized

        # Re-read what the parent allowed rather than the original: it has already been
        # through tinycss2 once and serialized, so this is parsing known-shaped CSS.
        kept = []
        for declaration in tinycss2.parse_declaration_list(sanitized):
            if declaration.type != "declaration":
                continue
            allowed_values = VALUE_ALLOW_LIST.get(declaration.lower_name)
            if allowed_values is not None:
                value = tinycss2.serialize(declaration.value).strip().lower()
                if value not in allowed_values:
                    continue
            kept.append(declaration)

        return tinycss2.serialize(kept).strip()
