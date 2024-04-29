from django.contrib import messages
from django.db import connection
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
        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)
        return render(request, 'library/confirm_import_quest.html', {'quest': quest})

    elif request.method == 'POST':

        dest_schema = connection.schema_name

        # Check if the quest already exists in the deck
        local_quest = Quest.objects.filter(import_id=quest_import_id).first()
        if local_quest:
            messages.warning(request, f"Your deck already has a quest named '{local_quest.name}' with the import_id {local_quest.import_id}.")
            return redirect('library:library_quest_list')

        with library_schema_context():
            quest = get_object_or_404(Quest, import_id=quest_import_id)

            quest_ids = [quest.import_id]
            import_quests_to(destination_schema=dest_schema, quest_import_ids=quest_ids)
            messages.success(request, f"Successfully imported '{quest.name}' to your deck.")

    return redirect('library:library_quest_list')
