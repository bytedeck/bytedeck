"""
Utility functions for use throughout the project
"""


def parse_code_markdown(html_string):
    """Takes a sample of html and replaces pairs of `backticks` with <code></code> tags """
    mkdn_code = "`"
    html_tag = "code"
    css_class = "backtick"
    while html_string.count(mkdn_code) >= 2:
        print(html_string)
        html_string = replace_next_pair_with_tag(html_string, mkdn_code, html_tag, css_class)

    return html_string


def replace_next_pair_with_tag(html_string, char, tag, css_class):
    html_string.replace(char, "<" + tag + " class=" + css_class + " >", 1)
    html_string.replace(char, "</" + tag + ">", 1)
    return html_string
