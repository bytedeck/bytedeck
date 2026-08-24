import functools
from uuid import UUID

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html, format_html_join
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

from hackerspace_online.decorators import staff_member_required
from tenant.views import NonPublicOnlyViewMixin

from quest_manager.models import Quest, Category

from siteconfig.models import SiteConfig
from tenant.models import Tenant
from tenant.tasks import send_email_message
from quest_manager.listing import QUEST_SORT_COLUMNS, search_quests
from utilities.sorting import apply_sort, resolve_sort

from notifications.signals import notify


from .exporter import export_quest_to_library, export_campaign_and_copy_quests
from .forms import ShareLicenceForm
from .importer import import_campaign_to, import_quest_to
from .models import ContentOrigin
from .transfer import LibraryTransferError, describe_validation_error
from .utils import (
    get_colliding_quest_names,
    get_library_conflicting_quests,
    get_library_schema_name,
    library_listable_quests,
    library_schema_context,
    load_library_quest_prereqs_for_render,
    load_library_quests_for_render,
)

User = get_user_model()


def shared_library_enabled_view(f):
    """Raise Http404 unless this deck has the Shared Library turned on.

    `SiteConfig.enable_shared_library` is off by default and marked experimental.
    Without this the flag only hid the sidebar link, so every Library URL stayed
    reachable (and importable) on a deck that had deliberately opted out. A deck
    with the feature off should behave as though it does not exist, hence 404
    rather than a 403 or an explanatory page.

    `SiteConfig.get()` returns None on the public schema, which has no deck
    config and so has no Shared Library either: that is treated the same way, so
    this holds on its own rather than relying on running after a non-public check.

    Args:
        f (callable): the view function to guard.

    Returns:
        callable: `f` wrapped so it only runs on a deck with the Library enabled.
    """
    @functools.wraps(f)
    def wrapper(request, *args, **kwargs):
        """Run the wrapped view only if this deck has the Shared Library on.

        Args:
            request (HttpRequest): the current request.
            *args: positional arguments for the wrapped view.
            **kwargs: keyword arguments for the wrapped view.

        Returns:
            HttpResponse: whatever the wrapped view returns.

        Raises:
            Http404: if the deck has the Shared Library off, or has no deck config.
        """
        config = SiteConfig.get()
        if config is None or not config.enable_shared_library:
            raise Http404("The Shared Library is not enabled on this deck.")
        return f(request, *args, **kwargs)
    return wrapper


def get_published_library_object(model, import_id):
    """Fetch a published object from the Shared Library by its import ID.

    Content lands in the Library unpublished and stays invisible to other decks
    until a Library admin reviews and publishes it (#1949). Both import paths go
    through here, so the gate holds against a POST straight to an import URL and
    not only against what the listing pages choose to show.

    Must be called from within the library schema context.

    Args:
        model (type[Quest] | type[Category]): the model to fetch.
        import_id (UUID): the import ID to look up.

    Returns:
        Quest | Category | None: the published object, or None when it exists in
        the Library but has not been published yet.

    Raises:
        Http404: if nothing in the Library has this import ID at all.
    """
    obj = model.objects.filter(import_id=import_id).first()
    if obj is None:
        raise Http404(f"No {model._meta.verbose_name} in the Library with import ID {import_id}.")

    return obj if obj.published else None


def redirect_awaiting_review(request, content_type, redirect_to):
    """Send the user back to the Library, explaining the content is not published yet.

    Args:
        request (HttpRequest): the current request, for the message framework.
        content_type (str): "quest" or "campaign", used in the message.
        redirect_to (str): the URL name to redirect to.

    Returns:
        HttpResponseRedirect: a redirect carrying the warning message.
    """
    messages.warning(
        request,
        f"That {content_type} is not available in the Library yet: a Library admin still has to review and publish it."
    )
    return redirect(redirect_to)


def viewer_is_library_staff(request):
    """Whether this viewer is staff *of the Library deck itself*.

    Attribution names the deck content came from, but a link to that deck is only useful
    to someone who can actually open it. A teacher on their own deck cannot: other decks
    are closed to them, so the link would be a dead end. The people it helps are the
    Library's own staff, who review pushed content and may want to see where it came from,
    and they are staff of the Library deck, which is only true when the page is being
    served from it.

    The deck is read from the request rather than from the connection, because the views
    that ask this read the content itself inside `library_schema_context()`: on the
    connection every viewer would look like they were on the Library deck.

    Args:
        request (HttpRequest): the current request.

    Returns:
        bool: True when the request is being served from the Library deck by a staff user.
    """
    return request.tenant.schema_name == get_library_schema_name() and request.user.is_staff


def redirect_failed_import(request, error, redirect_to):
    """Send the user back to the Library, explaining why the import did not happen.

    An import can fail for reasons the Library cannot see in advance, the common one being
    a quest name this deck already uses for something else. Nothing was written when this
    runs: the copy is atomic, so a campaign never lands half-imported. Telling the teacher
    which quest clashed is what lets them rename it and try again, rather than meeting a
    500 page or a bare 404 (#2364, #2397).

    Args:
        request (HttpRequest): the current request, for the message framework.
        error (LibraryTransferError): the failure, whose message names the content.
        redirect_to (str): the URL name to redirect to.

    Returns:
        HttpResponseRedirect: a redirect carrying the error message.
    """
    messages.error(
        request,
        f"That import could not be completed, so nothing was added to your deck. {error} "
        "Renaming your own copy and importing again should clear it."
    )
    return redirect(redirect_to)


def redirect_already_imported(request, local_object, content_type, redirect_to):
    """Send the user back, explaining that this deck already has the content.

    Content is matched across decks by `import_id`, so a deck that already holds this
    content holds *this* content, not something like it. Re-importing is refused because
    overwriting a deck's own copy is not supported yet (#2376), and the confirmation page
    says so and disables its button.

    That makes this the case where the button was not what was clicked: a stale tab, the
    back button, a resubmitted form, or two teachers importing at once. Meeting a bare 403
    there reads as "you are not allowed to do that", when what happened is that the deck
    already has it, so the answer names the local copy and links to it (#2373).

    Args:
        request (HttpRequest): the current request, for the message framework.
        local_object (Quest | Category): this deck's copy, which the message links to.
        content_type (str): "quest" or "campaign", used in the message.
        redirect_to (str): the URL name to redirect to.

    Returns:
        HttpResponseRedirect: a redirect carrying the warning message.
    """
    # format_html, not an f-string: every message is rendered through `|safe`
    # (`templates/messages-snippet.html`), so a name carrying markup would reach the page
    # as markup. The link below is ours and stays live; the name and URL are escaped.
    messages.warning(
        request,
        format_html(
            'Your deck already has this {}: <a href="{}">{}</a>. Nothing was imported, '
            'because replacing a {} you already have is not supported yet. Delete your '
            "copy first if you want the Library's version instead.",
            content_type, local_object.get_absolute_url(), local_object.name, content_type,
        )
    )
    return redirect(redirect_to)


def _describe_transfer_failure(error):
    """One readable sentence for either kind of failure a push can raise.

    Two exception types reach the same place. `LibraryTransferError` already reads as a
    sentence naming the content and the clash. A `ValidationError` does not: it carries a
    dict or list that renders with Django's punctuation, so it goes through the same
    formatting the transfer layer uses for the errors it wraps.

    Args:
        error (LibraryTransferError | ValidationError): the failure.

    Returns:
        str: the reason, ending in a full stop so it reads inside the surrounding message.
    """
    described = describe_validation_error(error) if isinstance(error, ValidationError) else str(error)

    return described if described.endswith('.') else f"{described}."


def redirect_failed_export(request, error, redirect_to):
    """Send the sharer back, explaining why their content did not reach the Library.

    A push can fail on something the sharer cannot see from their own deck, because the
    Library is another schema: a quest name or a campaign title that something else there
    already uses. Nothing was written when this runs, since the push is atomic.

    The mirror of `redirect_failed_import`, and it exists for the same reason: without it
    the failure escapes the view as an exception and the sharer meets a 500 page, after
    they have read and agreed to the licence, with nothing naming the cause (#2531, #2534).

    Renaming is the sharer's move to make rather than ours. The import direction resolves a
    clash by renaming the arriving copy, but that copy is a stranger to the receiving deck;
    here the clashing name is the sharer's own, on their own quest, and silently publishing
    it to every other deck under a name they did not choose is not a favour. Two quests
    called the same thing is also exactly what makes a Library hard to browse.

    Args:
        request (HttpRequest): the current request, for the message framework.
        error (Exception): the failure, whose message names the content and the clash.
        redirect_to (str): the URL name to redirect to.

    Returns:
        HttpResponseRedirect: a redirect carrying the error message.
    """
    messages.error(
        request,
        f"That share could not be completed, so nothing was added to the Library. {error} "
        "Renaming your copy and sharing again should clear it."
    )
    return redirect(redirect_to)


def redirect_already_shared(request, local_object, content_type, redirect_to):
    """Send the user back, explaining that the Library already has this content.

    The counterpart to `redirect_already_imported`, for a push that would land on a copy
    already in the Library. Pushing again is refused for the same reason in reverse:
    updating what is already there is not supported yet (#2376).

    The message names the content but does not link to the Library's copy, because a
    teacher cannot open another deck: the link would be a dead end.

    Args:
        request (HttpRequest): the current request, for the message framework.
        local_object (Quest | Category): the content that was being shared.
        content_type (str): "quest" or "campaign", used in the message.
        redirect_to (str): the URL name to redirect to.

    Returns:
        HttpResponseRedirect: a redirect carrying the warning message.
    """
    # format_html for the same reason as `redirect_already_imported`: messages render safe.
    messages.warning(
        request,
        format_html(
            "'{}' is already in the Library, so it was not shared again. Sharing an "
            "updated version of a {} that is already there is not supported yet.",
            local_object.name, content_type,
        )
    )
    return redirect(redirect_to)


def tell_importer_about_renamed_quests(request, renamed_quests):
    """Tell the importing teacher which arriving quests were given a name of their own.

    `Quest.name` is unique per deck, so a quest whose name this deck already uses is
    renamed on the way in rather than blocking the import (see `resolve_name_collisions`).
    The rename is silent otherwise, and a quest that is not called what the Library page
    said it was called is exactly the sort of thing a teacher goes looking for and cannot
    find, so it is named here along with what it is now called (#2364, #2397).

    Args:
        request (HttpRequest): the current request, for the message framework.
        renamed_quests (list[tuple[str, str]]): `(wanted_name, given_name)` pairs.

    Returns:
        None. Queues an informational message when anything was renamed, and does nothing
        when every quest kept the name it arrived with.
    """
    if not renamed_quests:
        return

    renames = ', '.join(f"'{wanted}' is now '{given}'" for wanted, given in renamed_quests)
    messages.info(
        request,
        f"Your deck already had a quest called '{renamed_quests[0][0]}', so the copy that "
        f"just arrived is called '{renamed_quests[0][1]}'. Rename it to whatever suits your deck."
        if len(renamed_quests) == 1 else
        f"Your deck already had quests with some of these names, so the arriving copies were "
        f"renamed: {renames}. Rename them to whatever suits your deck."
    )


def warn_sharer_about_dropped_common_data(request, dropped_common_data):
    """Tell the sharer that a quest's shared General Info block will not travel.

    `CommonData` is the block of text several quests can share (a marking rubric, how to
    record a video, lab safety rules). It has no `import_id`, so there is no key that
    means the same block in another deck's schema, and copying the raw id would attach the
    quest to whatever text happens to sit at that id there. Leaving it behind is therefore
    correct; the problem is that the quest arrives missing a panel its instructions may
    refer to, and nobody is told (#2398).

    Args:
        request (HttpRequest): the current request, for the message framework.
        dropped_common_data (list[str]): titles of the General Info blocks left behind.

    Returns:
        None. Queues a warning message when a block was left behind, and does nothing when
        the content did not use one.
    """
    if not dropped_common_data:
        return

    names = ', '.join(f"'{title}'" for title in dropped_common_data)
    messages.warning(
        request,
        f"The shared General Info {names} does not travel to the Library, so the copy "
        "there arrives without that panel. Paste the text into the quest instructions "
        "and share it again if this info is required in the quest."
        if len(dropped_common_data) == 1 else
        f"Shared General Info does not travel to the Library, so the copies there arrive "
        f"without those panels: {names}. Paste the text into the quest instructions and "
        "share them again if this info is required in the quests."
    )


def warn_sharer_about_skipped_quests(request, skipped_quests):
    """Tell the sharer which quests were left out of the campaign they just shared.

    A campaign push carries `Category.current_quests()`, which is published and not
    archived, so archiving a quest quietly removes it from everything shared afterwards.
    The push still succeeds and the campaign still looks complete, so without this the
    sharer has no way to notice: the gap only shows up on somebody else's deck, and only
    if they happen to know what was supposed to be there (#2442).

    Args:
        request (HttpRequest): the current request, for the message framework.
        skipped_quests (list[str]): names of the campaign's quests that were not shared.
            Only published ones: an archived draft would not travel after unarchiving
            either, so naming it would attach advice that does not work.

    Returns:
        None. Queues a warning message when anything was left behind, and does nothing
        when the whole campaign travelled.
    """
    if not skipped_quests:
        return

    names = ', '.join(f"'{name}'" for name in skipped_quests)
    messages.warning(
        request,
        f"{names} was not included, because archived quests are not shared. Unarchive it "
        "and share the campaign again if it should be part of what other decks receive."
        if len(skipped_quests) == 1 else
        f"These quests were not included, because archived quests are not shared: {names}. "
        "Unarchive them and share the campaign again if they should be part of what other "
        "decks receive."
    )


def warn_sharer_about_unmet_prereqs(request, unmet_prereqs, unmet_alternates=()):
    """Tell the sharer which prerequisites did not travel with the content they just shared.

    A prerequisite only crosses if the thing it points at is in the Library too. A rank or
    a course can never be, and a quest outside what is being pushed is simply not there
    yet, so those prerequisites are dropped at this end and the copy in the Library
    arrives without them.

    A lost OR alternative is the opposite loss, warned about separately (#2549): the
    prerequisite itself survives, so the copy arrives *stricter* than written, with one
    of the ways to meet it gone. The two need different fixes from the teacher (a quest
    that arrives without its prerequisite needs one re-added on the far side; a narrowed
    one needs the alternative shared alongside it), so telling them the copy has no
    prerequisite when it is narrowed would point them at the wrong one.

    Nobody downstream can tell either way, because the Library row simply carries less
    than the original: the teacher who imports it later has nothing to be warned about.

    That makes this the only place the losses are visible, and the sharer is also the one
    who can act on them, by widening what they share or by re-adding the prerequisite on
    the far side (#2399, #2450).

    Args:
        request (HttpRequest): the current request, for the message framework.
        unmet_prereqs (list[str]): names of the prerequisite targets that did not travel.
        unmet_alternates (list[str]): names of the OR alternatives that did not travel.

    Returns:
        None: the outcome is zero, one or two warnings queued on the message
        framework, one per kind of loss that actually happened.
    """
    # format_html(_join), not f-strings: every message is rendered through `|safe`,
    # so a markup-bearing quest or rank name must arrive pre-escaped.
    if unmet_prereqs:
        names = format_html_join(', ', "'{}'", ((name,) for name in unmet_prereqs))
        if len(unmet_prereqs) == 1:
            template = (
                "One thing did not travel: this content has {} as a prerequisite, which is not in "
                "the Library, so the copy there is missing that prerequisite and anyone importing "
                "the content will get it without that requirement. Sharing the whole campaign "
                "carries prerequisites between its own quests; a rank, grade, block or course "
                "cannot be shared at all."
            )
        else:
            template = (
                "Some things did not travel: this content has {} as prerequisites, which are not "
                "in the Library, so the copy there is missing those prerequisites and anyone "
                "importing the content will get it without those requirements. Sharing the whole "
                "campaign carries prerequisites between its own quests; a rank, grade, block or "
                "course cannot be shared at all."
            )
        messages.warning(request, format_html(template, names))

    if unmet_alternates:
        names = format_html_join(', ', "'{}'", ((name,) for name in unmet_alternates))
        if len(unmet_alternates) == 1:
            template = (
                "A prerequisite kept its main requirement but lost its OR alternative: {} is "
                "not in the Library, so where the prerequisite offered a second way for the "
                "content to become available, the copy no longer does. Anyone importing it "
                "gets the stricter version. Share the alternative too if both options should "
                "remain open."
            )
        else:
            template = (
                "Some prerequisites kept their main requirement but lost an OR alternative: {} "
                "are not in the Library, so where those prerequisites offered a second way for "
                "the content to become available, the copy no longer does. Anyone importing it "
                "gets the stricter version. Share the alternatives too if all options should "
                "remain open."
            )
        messages.warning(request, format_html(template, names))


def record_push_origin(content_type, import_ids, request, source_deck_url):
    """Record which deck and which user shared this content to the Library (#2377).

    Content travels under CC BY-SA 4.0, which asks for attribution, so the two halves of
    it (the deck and the person) are stored at push time. They are both already known
    here; nothing was keeping them.

    Must be called from *within* the library schema context: the origin rows live in the
    library schema beside the content they describe. Resolve `source_deck_url` on the
    source deck (`request.tenant.get_root_url()`) before entering that context.

    Args:
        content_type (str): `ContentOrigin.QUEST` or `ContentOrigin.CAMPAIGN`.
        import_ids (Iterable[UUID]): the import_ids of the content that was just pushed.
            A campaign push passes its quests' ids too, so each quest carries its own
            attribution when it is imported on its own.
        request (HttpRequest): the current request, for the sharing user and deck name.
        source_deck_url (str): root URL of the deck the content was shared from.
    """
    for import_id in import_ids:
        ContentOrigin.record(
            import_id=import_id,
            content_type=content_type,
            deck_name=request.tenant.name,
            deck_url=source_deck_url,
            shared_by=request.user.username,
        )


def email_library_staff_of_push(content_type, content_name, exported_obj, sharer, source_deck_url):
    """Email active Library staff that freshly pushed content is awaiting review.

    Shared content lands in the Library unpublished and must be reviewed and
    published manually before it is visible to other decks (#1949). This sends
    the staff that signal, in addition to the in-app notification.

    Must be called from *within* the library schema context: the staff list and
    the exported object's link are read from the library schema. The email is
    dispatched via the shared Celery task (queued on ``default``) so the share
    request doesn't block on SMTP. It is a no-op when no active staff member has
    an email address (e.g. only the ``deck_ai`` bot user is staff).

    Args:
        content_type (str): "quest" or "campaign", used in the subject/body.
        content_name (str): the human-readable name of the shared content.
        exported_obj (Quest | Category): the copy now in the library schema,
            used to build the review/publish link on the Library deck.
        sharer (User): the user who pushed the content, from the source deck.
        source_deck_url (str): the root URL of the deck the content was shared
            from, so reviewers can see (and visit) which deck it originated on.
            Resolve it on the source deck (``request.tenant.get_root_url()``)
            before entering the library schema context.
    """
    recipient_list = list(
        User.objects.filter(is_active=True, is_staff=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not recipient_list:
        return

    library_root_url = Tenant.objects.get(schema_name=get_library_schema_name()).get_root_url()
    review_url = f"{library_root_url.rstrip('/')}{exported_obj.get_absolute_url()}"

    subject = f"[ByteDeck Library] New {content_type} awaiting review: {content_name}"
    message = get_template("library/email/content_pushed.html").render({
        "sharer": sharer,
        "content_type": content_type,
        "content_name": content_name,
        "review_url": review_url,
        "source_deck_url": source_deck_url,
    })
    # on_commit, not straight away: the push that this announces is written in one
    # transaction, and an email is not recallable. Sending it inline would mean a reviewer
    # could be told to come and look at content that a later failure rolled back (#2372).
    transaction.on_commit(
        lambda: send_email_message.apply_async(args=[subject, message, recipient_list], queue="default")
    )


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class LibraryQuestListView(NonPublicOnlyViewMixin, TemplateView):
    """
    View for displaying a list of the quests the shared library holds.

    A quest is listed when it is published, not archived, and not sitting behind an
    unpublished campaign (see `library_listable_quests`). Access is restricted to logged-in
    staff users.
    """
    # Shared template, tab context determines which section is shown
    template_name = 'library/library_overview.html'

    #: Quests per page, matching the campaigns tab.
    paginate_by = 15

    #: The columns this tab can be ordered by, shared with the deck's own quest tabs since
    #: both list the same model through the same columns.
    SORT_COLUMNS = QUEST_SORT_COLUMNS

    def get_search_term(self):
        """The search term the user typed, from the `q` query parameter.

        Returns:
            str: the trimmed search term, or '' when the box was left empty.
        """
        return self.request.GET.get('q', '').strip()

    def get_page_number(self):
        """The page the user asked for, with anything below the first page treated as the first.

        `Paginator.get_page()` maps an out-of-range number to the *last* page, which is the
        right answer for a stale link to page 40 of a Library that has shrunk to 3 pages,
        and the wrong one for `?page=0` or `?page=-1`: those aren't a request for the end of
        the list, they're a number that isn't a page at all. Clamping them here keeps the
        useful half of that behaviour and drops the surprising half.

        Returns:
            int | str: the requested page, never below 1. Non-numeric input is passed
            through untouched, for `get_page()` to turn into the first page.
        """
        requested = self.request.GET.get('page')

        try:
            return max(int(requested), 1)
        except (TypeError, ValueError):
            return requested

    def get_sort(self):
        """The column the list is ordered by and its direction, from the `sort` parameter.

        Returns:
            tuple[str, bool]: the column key, '' when none applies, and whether it was
            asked for in reverse.
        """
        return resolve_sort(self.request, self.SORT_COLUMNS)

    def sort_library_quests(self, quests, column, descending):
        """Order the quests by the chosen column, before the page is cut from them.

        Ordering has to happen here rather than in the browser, because the browser only
        holds one page: sorting there answers a question about the page, not about the
        Library. `name` settles quests that tie, so paging through a sorted Library shows
        each one exactly once, and quests with no campaign sort last either way.

        Args:
            quests (QuerySet[Quest]): the quests to order.
            column (str): the column key, or '' to keep the Library's own order.
            descending (bool): whether to reverse the chosen column.

        Returns:
            QuerySet[Quest]: the ordered quests.
        """
        return apply_sort(quests, self.SORT_COLUMNS, column, descending, tie_break='name')

    def get_library_quests(self, search_term):
        """The listable Library quests, narrowed by the search term.

        Must be called from within the library schema context, and the queryset must be
        evaluated there too: the caller paginates it, which is what runs the queries.

        A quest matches on its own name, on its campaign's title, or on one of its tags,
        which is what the column headings promise the reader they can search by. Several
        words narrow the results rather than widening them: every word has to match
        something, though not all the same thing, so "recursion python" finds the quest
        named "Recursion: base cases" that is tagged python. Narrowing is the more useful
        of the two readings once the Library is big enough to need searching at all.

        Args:
            search_term (str): what the user typed, or '' for no filtering.

        Returns:
            QuerySet[Quest]: the matching quests, campaign and tags pre-fetched.
        """
        quests = library_listable_quests().select_related('campaign').prefetch_related('tags')

        return search_quests(quests, search_term)

    def get_context_data(self, **kwargs):
        """
        Populate context with a page of the shared library's listable quests.

        The Library is read one page at a time, since loading all of it into memory on
        every request does not survive a Library worth browsing (#2379). Searching and
        sorting happen in the database for the same reason, so they cover every quest
        rather than only the ones already sent to the browser (#2410).

        Args:
            **kwargs: keyword arguments passed through to `TemplateView.get_context_data`.

        Returns:
            dict: Template context including:
                - heading (str): Page title.
                - tab (str): Active tab identifier.
                - library_quests (list[Quest]): The current page of listable quests, with
                    related Campaign and tags prefetched.
                - page_obj (Page): The current page, for the pagination controls.
                - search_term (str): What the user searched for, to keep the box filled in.
                - sort_column (str): The column the list is ordered by, '' for the Library's
                    own order. Read by the sortable column headings.
                - sort_descending (bool): Whether that column is applied in reverse.
                - num_matching_quests (int): How many quests the search matched, across
                    every page.
                - num_quests (int): Number of listable quests in the Library, used for the UI
                    badge. This is the whole Library, not the search results, so the badge
                    doesn't change as the user types.
                - num_campaigns (int): Number of active Campaigns with importable quests,
                    used for the UI badge in the Campaign tab.

        Each listed quest carries an `origin` attribute (a `ContentOrigin` or None), so the
        list can attribute it to the deck and person who shared it (#2377).
        """
        context = super().get_context_data(**kwargs)
        search_term = self.get_search_term()

        sort_column, sort_descending = self.get_sort()

        with library_schema_context():
            quests = self.get_library_quests(search_term)
            quests = self.sort_library_quests(quests, sort_column, sort_descending)
            paginator = Paginator(quests, self.paginate_by)
            # get_page (rather than page) turns a junk or out-of-range ?page= into the
            # nearest real page instead of raising
            page = paginator.get_page(self.get_page_number())
            # Read inside the library context: the template renders this after the schema
            # has switched back to the caller's own deck.
            page_quests = load_library_quests_for_render(list(page.object_list))
            num_quests = library_listable_quests().count() if search_term else paginator.count
            num_campaigns = Category.objects.all_published_with_importable_quests().count()

            # One query for this page rather than one per row, and only for the quests
            # actually being rendered.
            origins = ContentOrigin.for_content(
                import_ids=[quest.import_id for quest in page_quests],
                content_type=ContentOrigin.QUEST,
            )
            for quest in page_quests:
                # Attached to the quest so the template can read it beside the quest's own
                # fields; quests shared before origins were recorded simply have None.
                quest.origin = origins.get(quest.import_id)

        context.update({
            'heading': 'Library',
            'tab': 'quests',
            'library_quests': page_quests,
            'page_obj': page,
            'search_term': search_term,
            'sort_column': sort_column,
            'sort_descending': sort_descending,
            'viewer_is_library_staff': viewer_is_library_staff(self.request),
            'num_matching_quests': paginator.count,
            'num_quests': num_quests,
            'num_campaigns': num_campaigns,
        })
        return context


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class LibraryCampaignListView(NonPublicOnlyViewMixin, TemplateView):
    """
    View for displaying a list of active campaigns (categories) from the shared library.

    Only campaigns that are active and contain at least one quest that is both
    published and not archived will be shown.
    Access is restricted to logged-in staff users.
    """
    # Shared template, tab context determines which section is shown
    template_name = 'library/library_overview.html'

    def get_context_data(self, **kwargs):
        """
        Populate context with active campaigns from the shared library.

        Args:
            **kwargs: keyword arguments passed through to `TemplateView.get_context_data`.

        Returns:
            dict: Template context including:
                - heading (str): Page title.
                - tab (str): Active tab identifier.
                - library_categories (QuerySet[Category]): A queryset of active campaigns
                    (categories) from the shared library. Each campaign includes at least one
                    quest that is:
                        - published=True
                        - archived=False (not archived)
                - num_campaigns (int): Number of campaigns in the displayed list, used for the UI badge.
                - num_quests (int): Total number of listable quests (published, not archived,
                    and not behind an unpublished campaign), used for the UI badge in the
                    quest tab. Read through the same helper the Quests tab lists with, so
                    the badge agrees whichever tab the user is on.
                - is_library_view (bool): True, so the campaign table shared with the deck's own
                    campaign list shows the Library's import action instead of the local ones.
        """
        context = super().get_context_data(**kwargs)

        with library_schema_context():
            # Explicitly call len() to force evaluation inside the library context
            # this forces all Campaigns to load.
            quests_count = library_listable_quests().count()
            campaigns = Category.objects.all_published_with_importable_quests()
            num_campaigns = len(campaigns)

        context.update({
            'heading': 'Library',
            'tab': 'campaigns',
            'library_categories': campaigns,
            'num_campaigns': num_campaigns,
            'num_quests': quests_count,
            'is_library_view': True,
        })
        return context


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class ImportQuestView(NonPublicOnlyViewMixin, View):
    """
    View for importing a single quest from the shared library into the current deck.

    Handles both GET and POST requests:
    - GET: Renders a confirmation page before importing.
    - POST: Performs the import if the quest does not already exist locally.

    Only accessible to authenticated staff users.
    """
    template_name = 'library/confirm_import_quest.html'

    def get(self, request, quest_import_id):
        """
        Display a confirmation page for importing the selected quest.

        Args:
            request (HttpRequest): The current HTTP request.
            quest_import_id (UUID): The import ID of the quest to import.

        Returns:
            HttpResponse: Rendered confirmation template with:
                - quest: The quest from the shared library.
                - local_quest: The local quest with a matching import_id, if one exists.
                - colliding_names: The quest's name, when a different local quest already
                  uses it and the copy will therefore arrive renamed.
        """
        # Look for a matching local quest (even if archived) to show a warning if it already exists
        local_quest = Quest.objects.all_including_archived().filter(import_id=quest_import_id).first()

        # Fetch the quest from the shared library
        with library_schema_context():
            quest = get_published_library_object(Quest, quest_import_id)

            if quest is not None:
                # The page renders outside this context, so everything it shows has to be
                # read in here (#2163, #2369). This preview is the one Library page that
                # names the quest's prerequisites, so it asks for those too (#2529).
                load_library_quests_for_render([quest])
                load_library_quest_prereqs_for_render([quest])

        if quest is None:
            return redirect_awaiting_review(request, 'quest', 'library:quest_list')

        return render(request, self.template_name, {
            'quest': quest,
            # A Quest from the local deck matching the import_id, or None if not found.
            'local_quest': local_quest,
            'colliding_names': get_colliding_quest_names([quest]),
        })

    def post(self, request, quest_import_id):
        """
        Import the selected quest into the current deck.

        Args:
            request (HttpRequest): The current HTTP request.
            quest_import_id (UUID): The import ID of the quest to import.

        Returns:
            HttpResponseRedirect: Redirects to the draft quests view on success.

            HttpResponseRedirect: back to the Library with an explanation when this deck
                already has the quest.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # The real check behind the confirmation page's disabled button, which a stale tab
        # or a resubmitted form gets past (#2373).
        local_quest = Quest.objects.all_including_archived().filter(import_id=quest_import_id).first()
        if local_quest:
            return redirect_already_imported(request, local_quest, 'quest', 'library:quest_list')

        with library_schema_context():
            quest = get_published_library_object(Quest, quest_import_id)
            if quest is None:
                return redirect_awaiting_review(request, 'quest', 'library:quest_list')
            # Use dest_schema because current schema is library
            try:
                imported = import_quest_to(destination_schema=dest_schema, quest_import_id=quest.import_id)
            except LibraryTransferError as error:
                return redirect_failed_import(request, error, 'library:quest_list')

        # Show a message with a link to the imported quest
        quest = get_object_or_404(Quest, import_id=quest_import_id)
        # An imported quest arrives as an unpublished draft with no prerequisite, so it is
        # invisible to students and unreachable on the map. Saying so is the difference
        # between "imported" and "usable", and each step links to the page that does it
        # rather than leaving the reader to find it (#2377).
        messages.success(
            request,
            format_html(
                "Successfully imported '<a href=\"{}\">{}</a>' to your deck. Two things left to do "
                'before students can see it: <strong><a href="{}">publish it</a></strong>, and give '
                'it a <strong><a href="{}">prerequisite</a></strong> so it is reachable on the '
                "quest map.",
                quest.get_absolute_url(), quest.name,
                reverse("quests:quest_update", args=[quest.id]),
                reverse("quests:quest_prereqs_update", args=[quest.id]),
            )
        )
        tell_importer_about_renamed_quests(request, imported.renamed_quests)

        return redirect('quests:drafts')


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class ImportCampaignView(NonPublicOnlyViewMixin, View):
    """
    View for importing a full campaign (category) from the shared library into the current deck.

    Handles both GET and POST requests:
    - GET: Displays a confirmation page with campaign and quest details.
    - POST: Imports all quests from the selected campaign.

    Only accessible to authenticated staff users.
    """
    template_name = 'library/confirm_import_campaign.html'

    def get(self, request, campaign_import_id):
        """
        Display a confirmation page for importing a campaign.

        Args:
            request (HttpRequest): The current HTTP request.
            campaign_import_id (UUID): The import ID of the campaign to import.

        Returns:
            HttpResponse: Renders the confirmation page with:
                - category: The shared library campaign.
                - local_category: A local campaign with the same import ID, if one exists.
                - shared_quests: List of quests currently associated with the campaign.
                - local_quest_import_ids: Set of import IDs for local quests that match.
                - Additional campaign details (name, icon, XP, quest count, etc.)
        """
        # Check if the campaign already exists locally
        local_category = Category.objects.filter(import_id=campaign_import_id).first()

        with library_schema_context():
            library_category = get_published_library_object(Category, campaign_import_id)
            if library_category is None:
                return redirect_awaiting_review(request, 'campaign', 'library:category_list')
            category_id = library_category.pk
            category_name = library_category.name
            category_icon = library_category.get_icon_url()
            category_quest_count = library_category.quest_count()
            category_total_xp_available = library_category.xp_sum()
            category_published = library_category.published

            # Read in the library, since the page renders after this context has closed.
            shared_quests = load_library_quests_for_render(list(library_category.current_quests()))
            # Extract import_ids from the list to compare with the local quests.
            quest_import_ids = [q.import_id for q in shared_quests]

        # Need local import_ids so the template can indicate which library quests already exist locally
        local_quests = list(Quest.objects.all_including_archived().filter(import_id__in=quest_import_ids))
        local_quest_import_ids = [quest.import_id for quest in local_quests]
        colliding_names = get_colliding_quest_names(shared_quests)

        context = {
            'category': library_category,
            'category_id': category_id,
            'category_name': category_name,
            'category_icon_url': category_icon,
            'category_quest_count': category_quest_count,
            'category_total_xp_available': category_total_xp_available,
            'category_published': category_published,
            'category_displayed_quests': shared_quests,
            'local_category': local_category,
            'local_quest_import_ids': local_quest_import_ids,
            'preservable_quests': local_quests,
            'colliding_names': colliding_names,
        }
        return render(request, self.template_name, context)

    def post(self, request, campaign_import_id):
        """
        Import all quests from the selected campaign into the current deck.

        Args:
            request (HttpRequest): The current HTTP request.
            campaign_import_id (UUID): The import ID of the campaign to import.

        Returns:
            HttpResponseRedirect: Redirects to the inactive campaigns view after import.

            HttpResponseRedirect: back to the Library with an explanation when this deck
                already has the campaign.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # The real check behind the confirmation page's disabled button, which a stale tab
        # or a resubmitted form gets past (#2373).
        local_category = Category.objects.filter(import_id=campaign_import_id).first()
        if local_category:
            return redirect_already_imported(request, local_category, 'campaign', 'library:category_list')

        with library_schema_context():
            category = get_published_library_object(Category, campaign_import_id)
            if category is None:
                return redirect_awaiting_review(request, 'campaign', 'library:category_list')
            # Collect import IDs for all quests in the campaign
            # Inactive quests are filtered out by the importer
            quest_ids = list(category.quest_set.values_list('import_id', flat=True))

        # Quests the teacher ticked to keep as they are. Parsed as UUIDs first, because a
        # value that is not one would raise rather than simply match nothing, then narrowed
        # twice: to quests belonging to the campaign being imported, and to quests this deck
        # actually holds. Both are needed against a hand-made POST, which could otherwise
        # name a quest this deck has in some other campaign and have it moved into this one.
        requested = set()
        for value in request.POST.getlist('preserve'):
            try:
                requested.add(UUID(value))
            except ValueError:
                continue
        requested &= set(quest_ids)

        preserve_import_ids = list(
            Quest.objects.all_including_archived()
            .filter(import_id__in=requested)
            .values_list('import_id', flat=True)
        )

        with library_schema_context():
            # Use dest_schema because current schema is library
            try:
                imported = import_campaign_to(
                    destination_schema=dest_schema, quest_import_ids=quest_ids,
                    campaign_import_id=category.import_id, preserve_import_ids=preserve_import_ids,
                )
            except LibraryTransferError as error:
                return redirect_failed_import(request, error, 'library:category_list')

        # Show a message with a link to the imported campaign
        category = get_object_or_404(Category, import_id=campaign_import_id)
        # As with a single quest: the campaign and its quests arrive unpublished and
        # unreachable, so the import is only half the job (#2377). Both remaining steps are
        # on the campaign's own page: the publish button there is the one that publishes
        # the quests too, and the quests are listed there for the one that needs a
        # prerequisite.
        # The edit form is deliberately not linked: ticking Published on it publishes the
        # campaign alone, leaving every quest a draft and students still seeing nothing.
        messages.success(
            request,
            format_html(
                "Successfully imported '<a href=\"{}\">{}</a>' to your deck. Two things left to do "
                'before students can see it: <strong><a href="{}">publish the campaign</a></strong> '
                "(which publishes its quests), and give its first quest a "
                '<strong><a href="{}">prerequisite</a></strong> so the campaign is reachable on the '
                "quest map.",
                category.get_absolute_url(), category.name,
                category.get_absolute_url(),
                category.get_absolute_url(),
            )
        )
        tell_importer_about_renamed_quests(request, imported.renamed_quests)

        # The campaign will be deactivated by import_campaign_to()
        return redirect('quests:categories_inactive')


class ExportPermissionMixin:
    """Guards the export endpoints with the same rule that decides whether to offer them.

    `SiteConfig.can_user_export_to_library` is that rule, and it is asked here rather than
    restated, so the endpoint and the Share buttons cannot drift apart. A second copy of the
    rule is worse than a long one: whichever clause it is missing becomes an endpoint that
    allows what no button offers, and nothing points at the difference (#2368).
    """

    def _require_export_permission(self, request):
        """Refuse the request unless this user may share from this deck.

        Args:
            request (HttpRequest): the current request, for the user and its deck.

        Returns:
            None. Returns normally when the export may proceed.

        Raises:
            PermissionDenied: if the user may not export. The message names the usual
                reason, which is a teacher sharing on a deck where the owner has not
                turned staff sharing on.
        """
        if not SiteConfig.get().can_user_export_to_library(request.user):
            raise PermissionDenied("Only the deck owner can export unless allow_staff_export is enabled.")


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class ExportQuestView(NonPublicOnlyViewMixin, ExportPermissionMixin, View):
    """
    View for exporting a single quest from the current deck into the shared library.

    Only the deck owner may export unless `allow_staff_export` is set to True.
    """
    template_name = 'library/confirm_export_quest.html'

    def get(self, request, quest_import_id):
        """
        Display the confirmation page for exporting a quest to the shared library.

        Args:
            request (HttpRequest): The current request object.
            quest_import_id (UUID): The import ID of the quest to export.

        Returns:
            HttpResponse: Rendered confirmation template with quest details.
        """
        self._require_export_permission(request)

        quest = get_object_or_404(Quest.objects.all(), import_id=quest_import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().filter(import_id=quest.import_id).first()
            colliding_names = get_colliding_quest_names([quest])

        return render(request, self.template_name, {
            'quest': quest,
            'library_quest': library_quest,
            'colliding_names': colliding_names,
            'licence_form': ShareLicenceForm(),
        })

    def post(self, request, quest_import_id):
        """
        Handle the export of a quest to the shared library.

        Steps:
            1. Validate user export permissions.
            2. Ensure the quest does not already exist in the library.
            3. Export the quest from the current schema to the library schema.
            4. Send a notification to the library owner.
            5. Display a success message to the exporter.

        Args:
            request (HttpRequest): The current request object.
            quest_import_id (UUID): The import ID of the quest to export.

        Returns:
            HttpResponseRedirect: Redirect to the main quests list after successful export.

            HttpResponseRedirect: back to the deck's quests with an explanation when the
                Library already has the quest.
        """
        self._require_export_permission(request)

        quest = get_object_or_404(Quest.objects.all(), import_id=quest_import_id)

        # The licence checkbox is `required` in the template, but that is a browser
        # hint only: this is what actually holds the push (#1546, #2366).
        licence_form = ShareLicenceForm(request.POST)
        if not licence_form.is_valid():
            with library_schema_context():
                library_quest = Quest.objects.all_including_archived().filter(import_id=quest.import_id).first()
            return render(request, self.template_name, {
                'quest': quest,
                'library_quest': library_quest,
                'licence_form': licence_form,
            })

        source_schema = connection.schema_name
        # Resolve the source deck's URL now, while its schema is active (the email
        # is built later inside the library schema context) -- see #1949.
        source_deck_url = request.tenant.get_root_url()

        with library_schema_context():
            already_shared = Quest.objects.all_including_archived().filter(import_id=quest.import_id).exists()
            colliding_names = get_colliding_quest_names([quest])

        if already_shared:
            return redirect_already_shared(request, quest, 'quest', 'quests:quests')

        if colliding_names:
            # Checked here as well as on the confirmation page, because that page can be
            # minutes old: another deck may have shared the name in between (#2531).
            return redirect_failed_export(
                request,
                f"The Library already has a different quest called '{colliding_names[0]}'.",
                'quests:quests',
            )

        # One transaction over the push, the notification it raises and the origin row it
        # records: a reviewer told to come and look at content, or an attribution pointing
        # at content, must not outlive a failure that rolled the content back (#2372).
        try:
            with transaction.atomic():
                shared = export_quest_to_library(source_schema=source_schema, quest_import_id=quest.import_id)

                with library_schema_context():
                    # Get the newly exported quest
                    exported_quest = Quest.objects.get(import_id=quest.import_id)

                    config = SiteConfig.get()
                    sender = config.deck_ai

                    recipients = User.objects.filter(is_active=True, is_staff=True)

                    # Notification sent to all active Library staff about the export
                    notify.send(
                        sender=sender,
                        recipient=None,
                        affected_users=list(recipients),
                        verb=f"{request.user} exported a quest to the library from {source_schema}:",
                        action=quest,
                        target=exported_quest,
                        icon="<i class='fa fa-book'></i>"
                    )

                    # Email active Library staff so they know there's a quest to review/publish (#1949).
                    email_library_staff_of_push("quest", quest.name, exported_quest, request.user, source_deck_url)

                    record_push_origin(ContentOrigin.QUEST, [quest.import_id], request, source_deck_url)
        except (LibraryTransferError, ValidationError) as error:
            # The guard above catches the clash this is usually raised for, so reaching here
            # means something neither the confirmation page nor that guard could know: a
            # name taken between the two requests, or a field the Library rejects. The
            # sharer has already agreed to the licence by this point, so the failure is
            # worth a reason they can act on.
            return redirect_failed_export(request, _describe_transfer_failure(error), 'quests:quests')

        # Success message displayed on local deck
        messages.success(
            request,
            format_html(
                "'<a href=\"{}\">{}</a>' has been shared to the Library. A Library admin has been "
                "notified: it will appear in the Library once they review and publish it.",
                quest.get_absolute_url(), quest.name,
            )
        )
        warn_sharer_about_unmet_prereqs(request, shared.unmet_prereqs, shared.unmet_alternates)
        warn_sharer_about_dropped_common_data(request, shared.dropped_common_data)
        return redirect('quests:quests')


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class ExportCampaignView(NonPublicOnlyViewMixin, ExportPermissionMixin, View):
    """
    View for exporting a full campaign (category) and its quests
    from the current deck into the shared library.

    Only the deck owner may export unless `allow_staff_export` is True.
    """
    template_name = 'library/confirm_export_campaign.html'

    def _render_confirmation(self, request, campaign, licence_form):
        """Render the campaign export confirmation page.

        Shared by GET and by the POST path that rejects an unagreed licence, so
        the page a user lands on after a failed submit is the one they started from.

        Args:
            request (HttpRequest): The current HTTP request object.
            campaign (Category): The local campaign being shared.
            licence_form (ShareLicenceForm): Blank on GET, bound (and invalid) on
                a rejected POST so its error renders.

        Returns:
            HttpResponse: The rendered confirmation template.
        """
        # evaluate the queryset to render the quests properly and give proper context to get_library_conflicting_quests
        quests = list(campaign.current_quests())

        # Get existing campaign in library (if any)
        with library_schema_context():
            existing_campaign = Category.objects.filter(import_id=campaign.import_id).first()
            # Clashes the Library would reject the push for, which the sharer cannot see
            # from their own deck. A title match on a *different* campaign is a clash;
            # the same campaign arriving again is `existing_campaign` above (#2534).
            colliding_title = (
                Category.objects.filter(title=campaign.title)
                .exclude(import_id=campaign.import_id)
                .values_list('title', flat=True)
                .first()
            )
            colliding_names = get_colliding_quest_names(quests)

        library_quest_import_ids = get_library_conflicting_quests(quests)

        context = {
            'campaign': campaign,
            'quests': quests,
            'existing_campaign': existing_campaign,
            'category_icon_url': campaign.get_icon_url(),
            'category_id': campaign.id,
            'category_quest_count': campaign.quest_count(),
            'category_total_xp_available': campaign.xp_sum(),
            'category_published': campaign.published,
            'category_displayed_quests': quests,
            'library_quest_import_ids': library_quest_import_ids,
            'colliding_title': colliding_title,
            'colliding_names': colliding_names,
            'licence_form': licence_form,
        }
        return render(request, self.template_name, context)

    def get(self, request, campaign_import_id):
        """
        Display the confirmation page for exporting a campaign and its quests to the shared library.

        Args:
            request (HttpRequest): The current HTTP request object.
            campaign_import_id (UUID): The unique import ID of the campaign to be exported.

        Returns:
            HttpResponse: The rendered confirmation template with campaign and quest details.
        """
        self._require_export_permission(request)

        campaign = get_object_or_404(Category, import_id=campaign_import_id)

        return self._render_confirmation(request, campaign, ShareLicenceForm())

    def post(self, request, campaign_import_id):
        """
        Handle the export of a campaign and its quests to the shared library.

        If any quests already exist in the library, copies will be created so
        the exported campaign has its own versions. Local quests are not affected.

        Args:
            request (HttpRequest): The current request object.
            campaign_import_id (UUID): The import ID of the campaign to export.

        Returns:
            HttpResponseRedirect: Redirect to the quests categories list on success.

            HttpResponseRedirect: back to the deck's campaigns with an explanation when the
                Library already has the campaign.
        """
        self._require_export_permission(request)

        campaign = get_object_or_404(Category, import_id=campaign_import_id)

        # The licence checkbox is `required` in the template, but that is a browser
        # hint only: this is what actually holds the push (#1546, #2366).
        licence_form = ShareLicenceForm(request.POST)
        if not licence_form.is_valid():
            return self._render_confirmation(request, campaign, licence_form)

        source_schema = connection.schema_name
        # Resolve the source deck's URL now, while its schema is active (the email
        # is built later inside the library schema context) -- see #1949.
        source_deck_url = request.tenant.get_root_url()

        with library_schema_context():
            already_shared = Category.objects.filter(import_id=campaign.import_id).exists()

        if already_shared:
            return redirect_already_shared(request, campaign, 'campaign', 'quests:categories')

        # Read this deck's quests before switching schemas: evaluated inside the Library
        # context the queryset would list the Library's quests for that campaign instead,
        # and report no clash at all (the lazy-evaluation trap of #2369 and #2529).
        quests = list(campaign.current_quests())

        with library_schema_context():
            colliding_title = (
                Category.objects.filter(title=campaign.title)
                .exclude(import_id=campaign.import_id)
                .values_list('title', flat=True)
                .first()
            )
            colliding_names = get_colliding_quest_names(quests)

        # Re-checked here as well as on the confirmation page, which can be minutes old
        # by the time it is submitted (#2534).
        if colliding_title:
            return redirect_failed_export(
                request,
                f"The Library already has a different campaign called '{colliding_title}'.",
                'quests:categories',
            )

        if colliding_names:
            return redirect_failed_export(
                request,
                f"The Library already has a different quest called '{colliding_names[0]}', "
                "which is in this campaign.",
                'quests:categories',
            )

        try:
            # One transaction over the push, the notification it raises and the origin rows it
            # records, for the same reason as the quest push above (#2372).
            with transaction.atomic():
                shared = export_campaign_and_copy_quests(source_schema=source_schema, campaign_import_id=campaign.import_id)

                with library_schema_context():
                    exported_campaign = Category.objects.get(import_id=campaign.import_id)

                    config = SiteConfig.get()
                    sender = config.deck_ai
                    recipients = User.objects.filter(is_active=True, is_staff=True)

                    notify.send(
                        sender=sender,
                        recipient=None,
                        affected_users=list(recipients),
                        verb=f"{request.user} exported a campaign to the library from {source_schema}:",
                        action=campaign,
                        target=exported_campaign,
                        icon="<i class='fa fa-book'></i>",
                    )

                    # Email active Library staff so they know there's a campaign to review/publish (#1949).
                    email_library_staff_of_push("campaign", campaign.name, exported_campaign, request.user, source_deck_url)

                    record_push_origin(ContentOrigin.CAMPAIGN, [campaign.import_id], request, source_deck_url)
                    # ...and each quest that travelled with it, so a quest imported on its own still
                    # says where it came from
                    record_push_origin(
                        ContentOrigin.QUEST,
                        exported_campaign.quest_set.values_list('import_id', flat=True),
                        request,
                        source_deck_url,
                    )
        except (LibraryTransferError, ValidationError) as error:
            # Reached when the Library rejects something the confirmation page could not
            # foresee: a name taken between the two requests, or a campaign left with no
            # publishable quest. Either way nothing landed, and saying so beats a 500.
            return redirect_failed_export(request, _describe_transfer_failure(error), 'quests:categories')

        messages.success(
            request,
            format_html(
                "'<a href=\"{}\">{}</a>' has been shared to the Library. A Library admin has been "
                "notified: it will appear in the Library once they review and publish it.",
                campaign.get_absolute_url(), campaign.name,
            )
        )
        warn_sharer_about_unmet_prereqs(request, shared.unmet_prereqs, shared.unmet_alternates)
        warn_sharer_about_skipped_quests(request, shared.skipped_quests)
        warn_sharer_about_dropped_common_data(request, shared.dropped_common_data)
        return redirect('quests:categories')


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class CategoryDetailView(NonPublicOnlyViewMixin, TemplateView):
    """
    View the content of a campaign (category) from the shared library.
    """
    template_name = 'library/category_detail_view.html'

    def get(self, request, *args, **kwargs):
        """Render the campaign, or send the user back if it is still awaiting review.

        Args:
            request (HttpRequest): The current HTTP request.
            *args: Positional arguments passed through to TemplateView.
            **kwargs: URL kwargs, including 'campaign_import_id' (UUID).

        Returns:
            HttpResponse: the campaign detail page, or a redirect to the Library
            campaign list when the campaign has not been published there yet.
        """
        with library_schema_context():
            category = get_published_library_object(Category, kwargs.get('campaign_import_id'))

        if category is None:
            return redirect_awaiting_review(request, 'campaign', 'library:category_list')

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """
        Extend context data with detailed information about a specific campaign (category)
        and its associated quests from the shared library schema.

        Args:
            **kwargs: Arbitrary keyword arguments, expected to include 'campaign_import_id' (UUID)
                    which identifies the campaign to fetch.

        Returns:
            dict: Context dictionary updated with:
                - category (Category): The campaign/category instance.
                - category_id (int): Primary key of the campaign.
                - category_campaign_name (str): Title of the campaign.
                - category_quest_count (int): Number of quests in the campaign.
                - category_total_xp_available (int): Sum of XP from all publsihed quests in the campaign.
                - category_displayed_quests (list[Quest]): List of quest objects to display.
                - quest_info (list[dict]): List of dicts with detailed quest info.
                - origin (ContentOrigin | None): Who shared this campaign and from which deck,
                    for the attribution the content's licence asks for (#2377). None for
                    campaigns shared before origins were recorded.
        """
        campaign_import_id = kwargs.get('campaign_import_id')
        context = super().get_context_data(**kwargs)

        with library_schema_context():
            category = get_object_or_404(Category, import_id=campaign_import_id)

            displayed_quests = load_library_quests_for_render(list(category.current_quests()))

            if displayed_quests:
                quest_info = [
                    {
                        'id': q.id,
                        'name': q.name,
                        'xp': q.xp,
                        'tags': list(q.tags.all()),
                        'published': q.published,
                        'expired': getattr(q, 'expired', False),
                    }
                    for q in displayed_quests
                ]
            else:
                quest_info = []

            origins = ContentOrigin.for_content(import_ids=[category.import_id], content_type=ContentOrigin.CAMPAIGN)

            context.update({
                'origin': origins.get(category.import_id),
                'viewer_is_library_staff': viewer_is_library_staff(self.request),
                'category': category,
                'category_id': category.pk,
                'category_campaign_name': category.title,
                'category_quest_count': category.quest_count(),
                'category_total_xp_available': category.xp_sum(),
                'category_displayed_quests': displayed_quests,
                'quest_info': quest_info,
            })

        return context
