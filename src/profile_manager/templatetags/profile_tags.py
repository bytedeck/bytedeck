"""Template tags for the lists of people a deck's pages offer: Yours, Current, All, Staff, TAs
and Archived."""
from django import template

from siteconfig.models import SiteConfig

register = template.Library()

#: What each list holds, shown as the hover text of its button wherever the app offers that list
#: (#2136), so the same name always means the same people. Each list of students holds the one
#: before it. {Students}, {students} and {group} are filled with the deck's own names for them.
PEOPLE_LIST_DESCRIPTIONS = {
    'yours': '{Students} registered in a course in an open semester, in a {group} you are assigned to as the teacher',
    'current': 'All {students} registered in a course in an open semester (includes all of yours)',
    'all': 'All non-archived {students} (includes all current {students})',
    'staff': 'All non-archived staff accounts',
    'tas': 'All {students} with the TA (Teaching Assistant) flag turned on, who can draft quests',
    'archived': ('Archived accounts, staff and {students}. Their data remains and teachers can still see it, '
                 'but they can no longer sign in (or join a course)'),
}


@register.simple_tag
def people_list_description(name):
    """The hover text of a list's button: what the list holds, in the deck's own words.

    Args:
        name (str): a key of PEOPLE_LIST_DESCRIPTIONS, such as 'yours' or 'archived'.

    Returns:
        str: the description, with the deck's custom names for a student and a group. Escaped
        when rendered, as those names are typed in Site Configuration.
    """
    config = SiteConfig.get()
    student = config.custom_name_for_student
    return PEOPLE_LIST_DESCRIPTIONS[name].format(
        Students=f'{student}s',
        students=f'{student.lower()}s',
        group=config.custom_name_for_group.lower(),
    )
