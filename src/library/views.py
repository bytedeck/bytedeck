from django.contrib import messages
from django.db import connection
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from quest_manager.models import Quest

from .importer import import_quests_to
from .utils import library_schema_context


def list_library_quests(request):
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


def import_quest_to_current_deck(request, quest_import_id):
    """
    Import a single quest to the current deck
    """

    if request.method == 'GET':
        # Check if the quest already exists in the deck
        local_quest = Quest.objects.filter(import_id=quest_import_id).first()

        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)

        print(local_quest)

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
            raise PermissionDenied(f"Quest with import_id {quest_import_id} already exists in the current deck.")

        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)

            quest_ids = [quest.import_id]
            import_quests_to(destination_schema=dest_schema, quest_import_ids=quest_ids)
            messages.success(request, f"Successfully imported '{quest.name}' to your deck.")

    return redirect('quests:drafts')
