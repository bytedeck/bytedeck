from django.contrib import messages
from django.db import connection
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth.decorators import login_required

from hackerspace_online.decorators import staff_member_required

from quest_manager.models import Quest, Category

from .importer import import_quests_to
from .utils import get_library_schema_name, library_schema_context


@method_decorator([login_required, staff_member_required], name='dispatch')
class LibraryQuestListView(TemplateView):
    """
    View for displaying a list of active quests from the shared library.

    Only quests that are both visible to students and unarchived will be displayed.
    Access is restricted to logged-in staff users.
    """
    template_name = 'library/library_quests.html'

    def get_context_data(self, **kwargs):
        """
        Populate context with active quests from the shared library.

        Returns:
            dict: Template context including:
                - heading (str): Page Title
                - library_quests (list): List of active Quest objects.
                - library_tab_active (bool): Used to highlight the active tab in the UI.
        """
        context = super().get_context_data(**kwargs)

        # Ensure queries happen inside the shared library schema
        with library_schema_context():
            # Explicitly call list() to force evaluation inside the context manager
            context.update({
                'heading': 'Quests',
                'library_quests': list(Quest.objects.get_active()),
                'library_tab_active': True,
            })
        return context


@method_decorator([login_required, staff_member_required], name='dispatch')
class LibraryCampaignListView(TemplateView):
    """
    View for displaying a list of active campaigns from the shared library.

    Only campaigns that are marked as active and contain at least one quest
    that is both visible to students and unarchived are included.
    Access restricted to logged-in staff users.
    """
    template_name = 'library/library_categories.html'

    def get_context_data(self, **kwargs):
        """
        Populate context with active campaigns from the shared library.

        Returns:
            dict: Template context including:
                - object_list (list): A list of active Category objects.
                - library_tab_active (bool): Used to highlight the active tab in the UI.
        """
        context = super().get_context_data(**kwargs)

        # Ensure query is executed within the library schema
        with library_schema_context():
            # Explicitly call list() to force evaluation inside the context manager
            context.update({
                'object_list': list(Category.objects.filter(active=True)),
                'library_tab_active': True,
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
            HttpResponse: Rendered template with the quest details from the library and
                          any matching local quest if one exists.
        """
        # Check for local existence to warn the user before importing
        local_quest = Quest.objects.filter(import_id=quest_import_id).first()

        # Fetch the quest from the shared library
        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)

        context = {
            'quest': quest,
            'local_quest': local_quest,
        }
        return render(request, self.template_name, context)

    def post(self, request, quest_import_id):
        """
        Import the selected quest into the current deck.

        Args:
            request (HttpRequest): The current HTTP request.
            quest_import_id (UUID): The import ID of the quest to import.

        Returns:
            HttpResponseRedirect: Redirects to the draft quest list upon success.

        Raises:
            PermissionDenied: If the quest already exists locally.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # Block import if quest already exists locally (shouldn't happen because import button would be disabled)
        if Quest.objects.filter(import_id=quest_import_id).exists():
            raise PermissionDenied(f'Quest with import_id {quest_import_id} already exists in the current deck.')

        # Import the quest from the shared library into the current schema
        with library_schema_context():
            # Get the quest to import
            quest = get_object_or_404(Quest, import_id=quest_import_id)
            # Import it to the local schema using dest_schema because current would be library
            import_quests_to(destination_schema=dest_schema, quest_import_ids=[quest.import_id])
            messages.success(request, f"Successfully imported '{quest.name}' to your deck.")

        return redirect('quests:drafts')


@method_decorator([login_required, staff_member_required], name='dispatch')
class ImportCampaignView(View):
    """
    View for importing a full campaign (category) from the shared library to the current deck.

    Handles both GET and POST requests:
    - GET: Displays a confirmation page with detailed campaign and quest info.
    - POST: Imports all quests in the campaign into the current schema.

    Access is restricted to authenticated staff users.
    """
    template_name = 'library/confirm_import_campaign.html'

    def get(self, request, campaign_import_id):
        """
        Display a confirmation page for importing a campaign from the shared library.

        Args:
            request (HttpRequest): The current HTTP request.
            campaign_import_id (UUID): The import ID of the campaign to import.

        Returns:
            HttpResponse: Rendered template with campaign and quest details from the library,
                          and any matching local category if one exists
        """
        # Check if the campaign already exists locally
        local_category = Category.objects.filter(import_id=campaign_import_id).first()

        # Fetch campaign and related quest data from the shared library
        with library_schema_context():
            category = get_object_or_404(Category, import_id=campaign_import_id)
            category_icon_url = category.get_icon_url()
            category_id = category.pk
            category_quest_count = category.quest_count()
            category_total_xp_available = category.xp_sum()
            category_active = category.active
            category_displayed_quests = list(category.quest_set.all())
            category_name = category.name

        context = {
            'local_category': local_category,
            'category': category,
            'category_id': category_id,
            'category_campaign_name': category_name,
            'category_icon_url': category_icon_url,
            'category_quest_count': category_quest_count,
            'category_total_xp_available': category_total_xp_available,
            'category_active': category_active,
            'category_displayed_quests': category_displayed_quests,
            'use_schema': get_library_schema_name(),
        }
        return render(request, 'library/confirm_import_campaign.html', context)

    def post(self, request, campaign_import_id):
        """
        Import all quests in the selected campaign into the current deck.

        Args:
            request (HttpRequest): The current HTTP request.
            campaign_import_id (UUID): The import ID of the campaign to import.

        Returns:
            HttpResponseRedirect: Redirects to the inactive campaigns page after import.

        Raises:
            PermissionDenied: if a campaign with the same import ID already exists locally.
        """
        # Set the local schema as dest_schema for later use
        dest_schema = connection.schema_name

        # Block import if campaign already exists locally (shouldn't happen because import button would be disabled)
        local_category_qs = Category.objects.filter(import_id=campaign_import_id)
        local_category = local_category_qs.first()
        if local_category:
            raise PermissionDenied(f'Campaign with name {campaign_import_id} already exists in the current deck.')

        # Fetch the campaign and import its quests
        with library_schema_context():
            category = get_object_or_404(Category, import_id=campaign_import_id)

            # Collect import IDs for all quests in the campaign
            # Inactive quests are filtered out by import_quests_to()
            quest_ids = list(category.quest_set.values_list('import_id', flat=True))
            # Import all quests in the list to dest_schema (local schema)
            import_quests_to(destination_schema=dest_schema, quest_import_ids=quest_ids)
            messages.success(request, f"Successfully imported '{category.name}' to your deck.")

        # Make the campaign inactive post-import
        # The quests are made inactive via import_quests_to()
        local_category_qs.update(active=False)
        return redirect('quest_manager:categories_inactive')
