import functools

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils.decorators import method_decorator
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

from notifications.signals import notify


from .exporter import export_quest_to_library, export_campaign_and_copy_quests
from .forms import ShareLicenceForm
from .importer import import_campaign_to, import_quest_to
from .models import ContentOrigin
from .transfer import LibraryTransferError
from .utils import get_library_schema_name, library_schema_context, get_library_conflicting_quests

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
    """
    @functools.wraps(f)
    def wrapper(request, *args, **kwargs):
        config = SiteConfig.get()
        if config is None or not config.enable_shared_library:
            raise Http404("The Shared Library is not enabled on this deck.")
        return f(request, *args, **kwargs)
    return wrapper


def get_published_library_object(model, import_id):
    """Fetch a published object from the Shared Library by its import ID.

    Content lands in the Library unpublished and stays invisible to other decks
    until a Library admin reviews and publishes it (#1949). That gate used to
    filter only the listing pages, so a POST straight to an import URL pulled
    unreviewed content down. Both import paths go through here instead.

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
        content_type (str): "quest" or "campaign" -- used in the subject/body.
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
    message = get_template("library/email/content_pushed.txt").render({
        "sharer": sharer,
        "content_type": content_type,
        "content_name": content_name,
        "review_url": review_url,
        "source_deck_url": source_deck_url,
    })
    send_email_message.apply_async(args=[subject, message, recipient_list], queue="default")


@method_decorator([login_required, staff_member_required, shared_library_enabled_view], name='dispatch')
class LibraryQuestListView(NonPublicOnlyViewMixin, TemplateView):
    """
    View for displaying a list of active quests from the shared library.

    Only quests that are both published and not archived
    will be shown. Access is restricted to logged-in staff users.
    """
    # Shared template, tab context determines which section is shown
    template_name = 'library/library_overview.html'

    #: Quests per page, matching the campaigns tab.
    paginate_by = 15

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

    def get_library_quests(self, search_term):
        """The active Library quests to list, narrowed by the search term.

        Must be called from within the library schema context, and the queryset must be
        evaluated there too: the caller paginates it, which is what runs the queries.

        A quest matches on its own name, on its campaign's title, or on one of its tags,
        which is what the column headings promise the reader they can search by. Several
        words narrow the results rather than widening them: every word has to match
        something, though not all the same thing, so "recursion python" finds the quest
        named "Recursion: base cases" that is tagged python. That is how the search box
        behaved when it filtered rows in the browser, and it is the more useful of the two
        readings once the Library is big enough to need narrowing.

        Args:
            search_term (str): what the user typed, or '' for no filtering.

        Returns:
            QuerySet[Quest]: the matching quests, campaign and tags pre-fetched.
        """
        quests = Quest.objects.get_active().select_related('campaign').prefetch_related('tags')

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

    def get_context_data(self, **kwargs):
        """
        Populate context with a page of active quests from the shared library.

        The Library is read one page at a time: the whole thing used to be loaded into
        memory and rendered on every request, which does not survive a Library worth
        browsing (#2379). Searching happens in the database for the same reason, so it
        covers every quest rather than only the ones already sent to the browser.

        Args:
            **kwargs: keyword arguments passed through to `TemplateView.get_context_data`.

        Returns:
            dict: Template context including:
                - heading (str): Page title.
                - tab (str): Active tab identifier.
                - library_quests (list[Quest]): The current page of active quests, with
                    related Campaign and tags prefetched.
                - page_obj (Page): The current page, for the pagination controls.
                - search_term (str): What the user searched for, to keep the box filled in.
                - num_matching_quests (int): How many quests the search matched, across
                    every page.
                - num_quests (int): Number of active quests in the Library, used for the UI
                    badge. This is the whole Library, not the search results, so the badge
                    doesn't change as the user types.
                - num_campaigns (int): Number of active Campaigns with importable quests,
                    used for the UI badge in the Campaign tab.

        Each listed quest carries an `origin` attribute (a `ContentOrigin` or None), so the
        list can attribute it to the deck and person who shared it (#2377).
        """
        context = super().get_context_data(**kwargs)
        search_term = self.get_search_term()

        with library_schema_context():
            quests = self.get_library_quests(search_term)
            paginator = Paginator(quests, self.paginate_by)
            # get_page (rather than page) turns a junk or out-of-range ?page= into the
            # nearest real page instead of raising
            page = paginator.get_page(self.get_page_number())
            # Force evaluation inside the library context: the template renders this after
            # the schema has switched back to the caller's own deck.
            page_quests = list(page.object_list)
            num_quests = Quest.objects.get_active().count() if search_term else paginator.count
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
                - num_quests (int): Total number of visible (published and not archived) quests,
                    used for the UI badge in the quest tab.
                - is_library_view (bool): True, so the campaign table shared with the deck's own
                    campaign list shows the Library's import action instead of the local ones.
        """
        context = super().get_context_data(**kwargs)

        with library_schema_context():
            # Explicitly call len() to force evaluation inside the library context
            # this forces all Campaigns to load.
            quests_count = Quest.objects.get_active().count()
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
        """
        # Look for a matching local quest (even if archived) to show a warning if it already exists
        local_quest = Quest.objects.all_including_archived().filter(import_id=quest_import_id).first()

        # Fetch the quest from the shared library
        with library_schema_context():
            quest = get_published_library_object(Quest, quest_import_id)

        if quest is None:
            return redirect_awaiting_review(request, 'quest', 'library:quest_list')

        return render(request, self.template_name, {
            'quest': quest,
            # A Quest from the local deck matching the import_id, or None if not found.
            'local_quest': local_quest,
        })

    def post(self, request, quest_import_id):
        """
        Import the selected quest into the current deck.

        Args:
            request (HttpRequest): The current HTTP request.
            quest_import_id (UUID): The import ID of the quest to import.

        Returns:
            HttpResponseRedirect: Redirects to the draft quests view on success.

        Raises:
            PermissionDenied: If a quest with the same import ID already exists locally.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # Block import if the quest already exists locally (shouldn't happen because import button would be disabled)
        if Quest.objects.all_including_archived().filter(import_id=quest_import_id).exists():
            raise PermissionDenied(f'Quest with import_id {quest_import_id} already exists in the current deck.')

        with library_schema_context():
            quest = get_published_library_object(Quest, quest_import_id)
            if quest is None:
                return redirect_awaiting_review(request, 'quest', 'library:quest_list')
            # Use dest_schema because current schema is library
            try:
                import_quest_to(destination_schema=dest_schema, quest_import_id=quest.import_id)
            except LibraryTransferError as error:
                return redirect_failed_import(request, error, 'library:quest_list')

        # Show a message with a link to the imported quest
        quest = get_object_or_404(Quest, import_id=quest_import_id)
        link = f'<a href="{quest.get_absolute_url()}">{quest.name}</a>'
        # An imported quest arrives as an unpublished draft with no prerequisite, so it is
        # invisible to students and unreachable on the map. Saying so is the difference
        # between "imported" and "usable", and each step links to the page that does it
        # rather than leaving the reader to find it (#2377).
        publish_link = f'<a href="{reverse("quests:quest_update", args=[quest.id])}">publish it</a>'
        prereq_link = f'<a href="{reverse("quests:quest_prereqs_update", args=[quest.id])}">prerequisite</a>'
        messages.success(
            request,
            f"Successfully imported '{link}' to your deck. Two things left to do before "
            f"students can see it: <strong>{publish_link}</strong>, and give it a "
            f"<strong>{prereq_link}</strong> so it is reachable on the quest map."
        )

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

            # Force evaluation of the queryset in the library to get full Quest objects for rendering.
            shared_quests = list(library_category.current_quests())
            # Extract import_ids from the list to compare with the local quests.
            quest_import_ids = [q.import_id for q in shared_quests]

        # Need local import_ids so the template can indicate which library quests already exist locally
        local_quest_import_ids = Quest.objects.filter(import_id__in=quest_import_ids).values_list('import_id', flat=True)

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

        Raises:
            PermissionDenied: If a campaign with the same import ID already exists locally.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # Block import if campaign already exists locally (shouldn't happen because import button would be disabled)
        local_category_qs = Category.objects.filter(import_id=campaign_import_id)
        if local_category_qs.exists():
            raise PermissionDenied(f'Campaign with import ID {campaign_import_id} already exists in the current deck.')

        with library_schema_context():
            category = get_published_library_object(Category, campaign_import_id)
            if category is None:
                return redirect_awaiting_review(request, 'campaign', 'library:category_list')
            # Collect import IDs for all quests in the campaign
            # Inactive quests are filtered out by the importer
            quest_ids = list(category.quest_set.values_list('import_id', flat=True))
            # Use dest_schema because current schema is library
            try:
                import_campaign_to(destination_schema=dest_schema, quest_import_ids=quest_ids, campaign_import_id=category.import_id)
            except LibraryTransferError as error:
                return redirect_failed_import(request, error, 'library:category_list')

        # Show a message with a link to the imported campaign
        category = get_object_or_404(Category, import_id=campaign_import_id)
        link = f'<a href="{category.get_absolute_url()}">{category.name}</a>'
        # As with a single quest: the campaign and its quests arrive unpublished and
        # unreachable, so the import is only half the job (#2377). Publishing is on the
        # campaign's own edit form; the prerequisite belongs to one of its quests, so that
        # step links to the campaign, where they are listed.
        publish_link = (
            f'<a href="{reverse("quests:category_update", args=[category.id])}">publish the campaign</a>'
        )
        prereq_link = f'<a href="{category.get_absolute_url()}">prerequisite</a>'
        messages.success(
            request,
            f"Successfully imported '{link}' to your deck. Two things left to do before "
            f"students can see it: <strong>{publish_link}</strong> (which publishes its "
            f"quests), and give its first quest a <strong>{prereq_link}</strong> so the campaign "
            "is reachable on the quest map."
        )

        # The campaign will be deactivated by import_campaign_to()
        return redirect('quests:categories_inactive')


class ExportPermissionMixin:
    def _require_export_permission(self, request):
        """
        Ensure the requesting user has permission to perform an export.

        A user is allowed to export if either:
        - They are the configured deck owner, or
        - `allow_staff_export` is enabled in the site configuration and the user is staff.

        Raises:
            PermissionDenied: If the requesting user does not have export permission.
        """
        config = SiteConfig.get()
        if not (config.allow_staff_export or request.user == config.deck_owner):
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

        return render(request, self.template_name, {
            'quest': quest,
            'library_quest': library_quest,
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

        Raises:
            PermissionDenied: If a quest with the same import ID already exists in the library.
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
            if Quest.objects.all_including_archived().filter(import_id=quest.import_id).exists():
                raise PermissionDenied(f"A quest with import_id {quest.import_id} already exists in the shared library.")

        # Perform export
        export_quest_to_library(source_schema=source_schema, quest_import_id=quest.import_id)

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

        # Success message displayed on local deck
        link = f'<a href="{quest.get_absolute_url()}">{quest.name}</a>'
        messages.success(
            request,
            f"'{link}' has been shared to the Library. A Library admin has been notified: "
            "it will appear in the Library once they review and publish it."
        )
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

        Raises:
            PermissionDenied: If a campaign with the same import ID already exists in the shared library.
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
            # Block if campaign already exists in library
            if Category.objects.filter(import_id=campaign.import_id).exists():
                raise PermissionDenied(
                    f"A campaign with import_id {campaign.import_id} already exists in the shared library."
                )

        # Export campaign and quests
        exported_campaign = export_campaign_and_copy_quests(source_schema=source_schema, campaign_import_id=campaign.import_id)

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

        link = f'<a href="{campaign.get_absolute_url()}">{campaign.name}</a>'
        messages.success(
            request,
            f"'{link}' has been shared to the Library. A Library admin has been notified: "
            "it will appear in the Library once they review and publish it."
        )
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

            displayed_quests = list(category.current_quests())

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
