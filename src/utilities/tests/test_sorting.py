from django.test import RequestFactory, SimpleTestCase

from utilities.sorting import resolve_sort


SORT_COLUMNS = {'name': 'name', 'xp': 'xp', 'campaign': 'campaign__title'}


class ResolveSortTest(SimpleTestCase):
    """What `resolve_sort` reads out of the `sort` query parameter, and what it falls back to."""

    def sort_for(self, query=''):
        """Resolve the sort for a request carrying `query`, against SORT_COLUMNS.

        Args:
            query (str): the query string, without the leading '?'.

        Returns:
            tuple[str, bool]: what `resolve_sort` returned.
        """
        return resolve_sort(RequestFactory().get(f'/?{query}'), SORT_COLUMNS)

    def test_resolve_sort__reads_the_column_and_its_direction(self):
        """A column the list offers is used, and a leading '-' asks for the reverse."""
        self.assertEqual(self.sort_for('sort=xp'), ('xp', False))
        self.assertEqual(self.sort_for('sort=-xp'), ('xp', True))

    def test_resolve_sort__no_default_means_the_lists_own_order(self):
        """Asked for nothing, or for a column that does not exist, and given no default,
        it reports no column, which leaves the queryset's own ordering alone."""
        self.assertEqual(self.sort_for(''), ('', False))
        self.assertEqual(self.sort_for('sort=colour'), ('', False))
        self.assertEqual(self.sort_for('sort=-colour'), ('', False))

    def test_resolve_sort__falls_back_to_the_default_column(self):
        """A list that names a default comes up sorted by it (#2623, #2624).

        The fallback covers a stale link and a typed one as well as an absent parameter,
        so a column that does not exist lands on the default rather than on the model's
        `Meta.ordering`, which is what the reader was not seeing an order in.
        """
        request = RequestFactory().get('/')
        self.assertEqual(resolve_sort(request, SORT_COLUMNS, default='name'), ('name', False))

        stale = RequestFactory().get('/?sort=colour')
        self.assertEqual(resolve_sort(stale, SORT_COLUMNS, default='name'), ('name', False))

    def test_resolve_sort__a_chosen_column_wins_over_the_default(self):
        """Clicking a heading still decides the order, in either direction."""
        chosen = RequestFactory().get('/?sort=-campaign')
        self.assertEqual(resolve_sort(chosen, SORT_COLUMNS, default='name'), ('campaign', True))
