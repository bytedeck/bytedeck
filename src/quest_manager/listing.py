"""Searching and ordering shared by the quest lists that are paginated a page at a time.

The deck's quest tabs and the Library's quests tab list the same model through the same
columns, so they search and order it the same way. Both are paginated, which is why this
happens in the database: a page is all the browser holds, so filtering or ordering there
answers a question about the page rather than about the list (#2379, #2410, #2582).
"""
from django.db.models import Q

#: The columns a quest list can be ordered by, mapped to the field the database orders on.
#: Tags are deliberately absent: a quest carries any number of them, so there is no one
#: value to order it by, and the search box already finds the quests carrying a given one.
QUEST_SORT_COLUMNS = {
    'name': 'name',
    'xp': 'xp',
    'campaign': 'campaign__title',
}


def search_quests(quests, search_term):
    """Narrow a quest list to those matching every word of a search term.

    A quest matches a word on its own name, on its campaign's title, or on one of its
    tags, which is what the column headings promise the reader they can search by.

    Several words narrow the results rather than widening them: every word has to match
    something, though not all the same thing, so "recursion python" finds the quest named
    "Recursion: base cases" that is tagged python. Narrowing is the more useful of the two
    readings once a list is long enough to need searching at all.

    Args:
        quests (QuerySet[Quest]): the quests to narrow.
        search_term (str): what the user typed, or '' for no filtering.

    Returns:
        QuerySet[Quest]: the matching quests.
    """
    for word in search_term.split():
        quests = quests.filter(
            Q(name__icontains=word)
            | Q(campaign__title__icontains=word)
            | Q(tags__name__icontains=word)
        )

    if search_term:
        # distinct() because the tags join multiplies a quest by its matching tags
        quests = quests.distinct()

    return quests
