from django_summernote.settings import ALLOWED_TAGS, STYLES

# Extend a list of allowed tags (mandatory for ByteDeck project),
ALLOWED_TAGS += [
    # allow extra tags, fix #1340
    "pre",
    "kbd",
    "var",
    "mark",
    "small",
    "ins",
    "del",
    "samp",
    "font",
    "iframe",
    "hr",
    "figure",
    "figcaption",
    "address",
    "dl",
    "dt",
    "dd",
    "th",
    "caption",
    # Bootstrap Blockquotes
    "footer",
    "cite",
    # HTML5 media
    "video",
    "audio",
    "source",
    "track",
    # MathML (mandatory for ByteDeck project)
    "math",
    "maction",
    "menclose",
    "merror",
    "mfenced",
    "mfrac",
    "mglyph",
    "mi",
    "mlabeledtr",
    "mmultiscripts",
    "mn",
    "mo",
    "mover",
    "mpadded",
    "mphantom",
    "mroot",
    "mrow",
    "ms",
    "mspace",
    "msqrt",
    "mstyle",
    "msub",
    "msup",
    "msubsup",
    "mtable",
    "mtd",
    "mtext",
    "mtr",
    "munder",
    "munderover",
    "none",
    "mprescripts",
    "semantics",
    "annotation",
    "annotation-xml",
    # The inline SVG KaTeX draws with, for the parts of an expression that stretch to fit
    # what they contain: the square-root radical, extensible arrows, over- and underbraces,
    # and the tall delimiters around a matrix. Without these the maths still has its MathML
    # and its spans, so it lays out but comes up missing those strokes (#2763).
    #
    # Only the three elements KaTeX emits, rather than SVG at large: the ones left out are
    # how SVG carries script (script, foreignObject, animate and the rest of the animation
    # elements, and use with an xlink:href), and no allow-list that leaves them out has to
    # reason about them.
    "svg",
    "path",
    "line",
]

# Extend a list of allowed CSS properties (mandatory for ByteDeck project),
STYLES += [
    # allow extra styles, fix #1340
    "float",
    "height",
    "list-style",
    "list-style-type",
    "margin-left",
    "margin-right",
    "text-align",
    "text-decoration",
    "text-indent",
    "width",
    "scope",
    # What KaTeX lays an expression out with (#2763). It sets these per element, worked out
    # from the maths, so they cannot come from the stylesheet: the row heights and baseline
    # shifts that stack a fraction or an exponent, the offsets positioning a radical over
    # its contents, and the rule widths that draw a fraction bar or an \overline. Dropping
    # them leaves every part of the expression at the same baseline, which is the pile of
    # overlapping symbols the bug reports.
    #
    # "position" is restricted to the values KaTeX asks for by CSSSanitizer, since it is
    # what lets an element leave the flow and cover the page.
    "border-bottom-width",
    "border-right-width",
    "border-style",
    "border-top-width",
    "border-width",
    "bottom",
    "left",
    "min-width",
    "padding-left",
    "position",
    "top",
    "vertical-align",
]
