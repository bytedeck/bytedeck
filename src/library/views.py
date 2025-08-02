from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required

from hackerspace_online.decorators import staff_member_required

from quest_manager.models import Quest, Category

from .importer import import_campaign_to, import_quest_to
from .utils import get_library_schema_name, library_schema_context


@method_decorator([login_required, staff_member_required], name='dispatch')
class LibraryQuestListView(TemplateView):
    """
    View for displaying a list of active quests from the shared library.

    Only quests that are both published and not archived
    will be shown. Access is restricted to logged-in staff users.
    """
    # Shared template, tab context determines which section is shown
    template_name = 'library/library_overview.html'

    def get_context_data(self, **kwargs):
        """
        Populate context with active quests from the shared library.

        Returns:
            dict: Template context including:
                - heading (str): Page title.
                - tab (str): Active tab identifier.
                - library_quests (QuerySet[Quest]): Evaluated queryset of active quest objects,
                    with related Campaign and tags prefetched.
                - num_quests (int): Number of quests in the displayed list, used for the UI badge.
                - num_campaigns (int): Number of active Campaigns with importable quests,
                    used for the UI badge in the Campaign tab.
        """
        context = super().get_context_data(**kwargs)

        with library_schema_context():
            # Explicitly call len() to force evaluation inside the library context
            # this forces all quests to load.
            quests = Quest.objects.get_active().select_related('campaign').prefetch_related('tags')
            num_quests = len(quests)
            num_campaigns = Category.objects.all_published_with_importable_quests().count()

        context.update({
            'heading': 'Library',
            'tab': 'quests',
            'library_quests': quests,
            'num_quests': num_quests,
            'num_campaigns': num_campaigns,
        })
        return context


@method_decorator([login_required, staff_member_required], name='dispatch')
class LibraryCampaignListView(TemplateView):
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

        Returns:
            dict: Template context including:
                - heading (str): Page title.
                - tab (str): Active tab identifier.
                - library_campaigns (QuerySet[Category]): A queryset of active campaigns
                    (categories) from the shared library. Each campaign includes at least one
                    quest that is:
                        - published=True
                        - archived=False (not archived)
                - num_campaigns (int): Number of campaigns in the displayed list, used for the UI badge.
                - num_quests (int): Total number of visible (published and not archived) quests,
                    used for the UI badge in the quest tab.
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
        })
        return context


@method_decorator([login_required, staff_member_required], name='dispatch')
class ImportQuestView(View):
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
            quest = get_object_or_404(Quest, import_id=quest_import_id)

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
            quest = get_object_or_404(Quest, import_id=quest_import_id)
            # Use dest_schema because current schema is library
            import_quest_to(destination_schema=dest_schema, quest_import_id=quest.import_id)

        # Show a message with a link to the imported quest
        quest = get_object_or_404(Quest, import_id=quest_import_id)
        link = f'<a href="{quest.get_absolute_url()}">{quest.name}</a>'
        messages.success(request, f"Successfully imported '{link}' to your deck.")

        return redirect('quests:drafts')


@method_decorator([login_required, staff_member_required], name='dispatch')
class ImportCampaignView(View):
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
            library_category = get_object_or_404(Category, import_id=campaign_import_id)
            category_id = library_category.pk
            category_name = library_category.name
            category_icon = library_category.get_icon_url()
            category_quest_count = library_category.quest_count()
            category_total_xp_available = library_category.xp_sum()
            category_published = library_category.published

            shared_quests = list(library_category.current_quests())
            quest_import_ids = [q.import_id for q in shared_quests]

        # Get just the import IDs of matching local quests
        local_quest_import_ids = set(
            Quest.objects.filter(import_id__in=quest_import_ids).values_list('import_id', flat=True)
        )

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
            'use_schema': get_library_schema_name(),
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
            category = get_object_or_404(Category, import_id=campaign_import_id)
            # Collect import IDs for all quests in the campaign
            # Inactive quests are filtered out by the importer
            quest_ids = list(category.quest_set.values_list('import_id', flat=True))
            # Use dest_schema because current schema is library
            import_campaign_to(destination_schema=dest_schema, quest_import_ids=quest_ids, campaign_import_id=category.import_id)

        # Show a message with a link to the imported campaign
        category = get_object_or_404(Category, import_id=campaign_import_id)
        link = f'<a href="{category.get_absolute_url()}">{category.name}</a>'
        messages.success(request, f"Successfully imported '{link}' to your deck.")

        # The campaign will be deactivated by import_campaign_to()
        return redirect('quest_manager:categories_inactive')


@method_decorator([login_required, staff_member_required], name='dispatch')
class CategoryDetailView(TemplateView):
    """
    View the content of a campaign (category) from the shared library.
    """
    template_name = 'library/category_detail_view.html'

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
                - use_schema (str): Name of the library schema currently in use.
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

            context.update({
                'category': category,
                'category_id': category.pk,
                'category_campaign_name': category.title,
                'category_quest_count': category.quest_count(),
                'category_total_xp_available': category.xp_sum(),
                'category_displayed_quests': displayed_quests,
                'quest_info': quest_info,
                'use_schema': get_library_schema_name(),
            })

        return context
