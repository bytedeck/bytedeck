"""How a competency is linked wherever it's listed: its name, as a link to its page
(CompetencyDetailView), with the competency in full (Competency.full_text: course, category, the
whole name and its description) as the link's hover text, so a name cut short on a crowded page can
still be read in full.
"""
from django.template.defaultfilters import truncatechars
from django.utils.html import format_html


def competency_link(competency, length=None, new_tab=False, text=None):
    """ A link to a competency's page, named by the competency.

    Args:
        competency (Competency): the competency.
        length (int or None): cut the name short to this many characters (with an ellipsis), or show it
            in full when None.
        new_tab (bool): open the page in a new tab, for a link inside a form, so following it doesn't
            lose what has been entered.
        text (str or None): what the link says instead of the name.

    Returns:
        SafeString: the link.
    """
    label = text if text is not None else competency.name
    if length:
        label = truncatechars(label, length)
    target = format_html(' target="_blank" rel="noopener"') if new_tab else ''
    return format_html(
        '<a href="{}" title="{}"{}>{}</a>', competency.get_absolute_url(), competency.full_text, target, label,
    )
