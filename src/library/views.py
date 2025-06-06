from django.contrib import messages
from django.db import connection
from django.contrib.auth.decorators import login_required
from hackerspace_online.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from quest_manager.models import Quest
from quest_manager.models import Category

from .importer import import_quests_to
from .utils import get_library_schema_name, library_schema_context


@login_required
@staff_member_required
def quests_library_list(request):
    """
    Display a list of all active quests available in the shared library

    Args:
        request: HttpRequest object containing request data

    Returns:
        HttpResponse: Rendered template with library quests context
    """

    with library_schema_context():
        # Get the active quests and force the query to run while still in the library schema
        # by calling list() on the queryset
        library_quests = list(Quest.objects.get_active())

        context = {
            'heading': 'Quests',
            'library_quests': library_quests,
            'library_tab_active': True,
        }

    return render(request, 'library/library_quests.html', context)


@login_required
@staff_member_required
def campaigns_library_list(request):
    """
    Display a list of all active campaigns (categories) available in the shared library.

    Args:
        request: HttpRequest object containing request data

    Returns:
        HttpResponse: Rendered template with library categories context
    """

    with library_schema_context():
        # Get the active quests and force the query to run while still in the library schema
        # by calling list() on the queryset
        library_categories = list(Category.objects.filter(active=True))

        context = {
            'object_list': library_categories,
            'library_tab_active': True,
        }

    return render(request, 'library/library_categories.html', context)


@login_required
@staff_member_required
def import_quest_to_current_deck(request, quest_import_id):
    """
    Import a quest from the library to the current deck.

    Args:
        request: HttpRequest object containing request data
        quest_import_id: String ID of the quest to import

    Returns:
        HttpResponse: GET requests return rendered confirmation template
        HttpResponseRedirect: POST requests redirect to drafts view
    """

    if request.method == 'GET':
        # Check if the quest already exists in the deck
        local_quest = Quest.objects.filter(import_id=quest_import_id).first()

        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)

        context = {
            'quest': quest,
            'local_quest': local_quest,
        }
        return render(request, 'library/confirm_import_quest.html', context)

    elif request.method == 'POST':
        dest_schema = connection.schema_name

        # If the quest already exists in the destination schema, throw 404.
        # Shouldn't get here because the "Import" button is disabled
        local_quest = Quest.objects.filter(import_id=quest_import_id).first()
        if local_quest:
            raise PermissionDenied(f'Quest with import_id {quest_import_id} already exists in the current deck.')

        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)
            quest_ids = [quest.import_id]
            import_quests_to(destination_schema=dest_schema, quest_import_ids=quest_ids)
            messages.success(request, f"Successfully imported '{quest.name}' to your deck.")

    return redirect('quests:drafts')


@login_required
@staff_member_required
def import_campaign(request, campaign_name):
    """
    Import all quests from a specified campaign (category) to the current deck.

    Args:
        request: HttpRequest object containing request data
        campaign_name: String name of the campaign to import

    Returns:
        HttpResponse: GET requests return rendered confirmation template
        HttpResponseRedirect: POST requests redirect to inactive categories view
    """

    if request.method == 'GET':
        # Check if the quest already exists in the deck
        local_category = Category.objects.filter(title=campaign_name).first()

        # Fetch and load the items, and include them in the context so we get the correct
        # value from the database while we are still within the lbrary schema context.
        with library_schema_context():
            category = get_object_or_404(Category, title=campaign_name)
            category_icon_url = category.get_icon_url()
            category_id = category.pk
            category_quest_count = category.quest_count()
            category_total_xp_available = category.xp_sum()
            category_active = category.active
            category_displayed_quests = list(category.quest_set.all())

        context = {
            'local_category': local_category,
            'category': category,
            'category_id': category_id,
            'category_campaign_name': campaign_name,
            'category_icon_url': category_icon_url,
            'category_quest_count': category_quest_count,
            'category_total_xp_available': category_total_xp_available,
            'category_active': category_active,
            'category_displayed_quests': category_displayed_quests,
            'use_schema': get_library_schema_name(),
        }
        return render(request, 'library/confirm_import_campaign.html', context)

    elif request.method == 'POST':
        dest_schema = connection.schema_name

        # If the quest already exists in the destination schema, throw 404.
        # Shouldn't get here because the "Import" button is disabled

        local_category_qs = Category.objects.filter(title=campaign_name)

        local_category = local_category_qs.first()
        if local_category:
            raise PermissionDenied(f'Campaign with name {campaign_name} already exists in the current deck.')

        with library_schema_context():
            category = get_object_or_404(Category, title=campaign_name)

            # Import all quests
            quest_ids = list(category.quest_set.values_list('import_id', flat=True))
            import_quests_to(destination_schema=dest_schema, quest_import_ids=quest_ids)
            messages.success(request, f"Successfully imported '{category.name}' to your deck.")

        # Set the campaign to inactive after importing
        local_category_qs.update(active=False)
    return redirect('quest_manager:categories_inactive')
