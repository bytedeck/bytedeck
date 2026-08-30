"""Server-side column sorting, for lists that are sent to the browser one page at a time.

bootstrap-table's `data-sortable` reorders the rows the browser is holding. On a paginated
list that is one page, so the sort answers a question about the page rather than about the
list (#2410, #2582). These helpers move the decision to the database, where the whole list
is, and `templates/snippets/sortable_column_heading.html` renders the headings that drive
them.
"""
from django.db.models import F


def resolve_sort(request, sort_columns, default=''):
    """The column a list is ordered by and its direction, from the `sort` query parameter.

    A leading '-' asks for the reverse, which is Django's own `order_by` spelling and what
    the column headings put in their links. A column the list does not offer is ignored
    rather than refused, so a stale link, or one somebody typed, falls back to `default`
    instead of erroring.

    `default` is the column the list comes up sorted by before anyone clicks a heading. A
    list that names one is sorted by something the reader can see and can be told about,
    since the heading for the returned column draws its arrow (#2623, #2624). Leaving it
    empty keeps the model's own `Meta.ordering` instead, for a list whose natural order is
    the useful one.

    Args:
        request (HttpRequest): the current request.
        sort_columns (dict): the columns this list offers, keyed by the key its headings
            use, valued by what `apply_sort` should order on.
        default (str): the column key to fall back on, or '' to keep the list's own order.

    Returns:
        tuple[str, bool]: the column key, `default` when none applies, and whether it was
        asked for in reverse.
    """
    requested = request.GET.get('sort', '')
    descending = requested.startswith('-')
    column = requested[1:] if descending else requested

    if column not in sort_columns:
        return default, False

    return column, descending


def apply_sort(queryset, sort_columns, column, descending, tie_break):
    """Order a queryset by the chosen column, before a page is cut from it.

    `tie_break` is appended so the ordering is total. Rows that tie on the chosen column
    otherwise have no defined order between them, and the database is free to return them
    differently on each query, which is what lets a row appear on two pages or on neither
    as the reader pages through.

    Nulls sort last either way, rather than the blanks filling the first page when someone
    asks to see a list by a column many rows leave empty.

    Args:
        queryset (QuerySet): the rows to order.
        sort_columns (dict): the columns this list offers, valued by a field name or a
            query expression to order on.
        column (str): the chosen column's key, or '' to keep the list's own order.
        descending (bool): whether to reverse it.
        tie_break (str): a field that is unique enough to settle rows that tie.

    Returns:
        QuerySet: the ordered rows, or the queryset untouched when no column applies.
    """
    if not column:
        return queryset

    field = sort_columns[column]
    if isinstance(field, str):
        field = F(field)

    ordering = field.desc(nulls_last=True) if descending else field.asc(nulls_last=True)

    return queryset.order_by(ordering, tie_break)
