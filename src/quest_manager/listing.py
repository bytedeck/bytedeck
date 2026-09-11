"""Searching and ordering for the quest lists that are paginated a page at a time.

The deck's quest tabs and the Library's quests tab list the same model through the same
columns, so they search and order it the same way. The approvals and submissions tabs list
submissions of those quests, and search them by what their own columns show.

All of it happens in the database because all of these lists are paginated: a page is what
the browser holds, so filtering or ordering there answers a question about the page rather
than about the list (#2379, #2410, #2582, #2597).
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


def search_submissions(submissions, search_term, *, campaign=False, user=False):
    """Narrow a submission list to those matching every word of a search term.

    Each tab searches what its own columns show, which is why the two flags exist: the
    approvals tabs name the student and the submissions tabs name the campaign and tags.
    Searching a column a tab does not display would return rows whose match the reader
    cannot see, which reads as the list ignoring what they typed.

    The student is matched on the two things the User column shows: their username, and
    the preferred full name under it, which is `preferred_name` (falling back to the
    account's first name) plus the last name. All four are searched, so a teacher who
    types a surname finds the submission whether or not that student set a preferred name.

    Several words narrow the results rather than widening them, matching the quest lists.

    Args:
        submissions (QuerySet[QuestSubmission]): the submissions to narrow.
        search_term (str): what the user typed, or '' for no filtering.
        campaign (bool): whether this tab shows the quest's campaign and tags.
        user (bool): whether this tab shows whose submission it is.

    Returns:
        QuerySet[QuestSubmission]: the matching submissions.
    """
    for word in search_term.split():
        matches = Q(quest__name__icontains=word)

        if campaign:
            matches |= Q(quest__campaign__title__icontains=word) | Q(quest__tags__name__icontains=word)

        if user:
            matches |= (
                Q(user__username__icontains=word)
                | Q(user__profile__preferred_name__icontains=word)
                | Q(user__first_name__icontains=word)
                | Q(user__last_name__icontains=word)
            )

        submissions = submissions.filter(matches)

    if search_term and campaign:
        # distinct() because the tags join multiplies a submission by its matching tags
        submissions = submissions.distinct()

    return submissions
