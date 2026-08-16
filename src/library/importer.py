from django.db import transaction
from django_tenants.utils import schema_context
from quest_manager.models import Quest, Category

from .transfer import snapshot_quest, write_quests
from .utils import library_schema_context


def import_campaign_to(*, destination_schema, quest_import_ids, campaign_import_id):
    """
    Imports the given campaign and all quests from the library schema into the given destination schema.

    Imported quests arrive as drafts, except where the destination deck already has the
    quest: re-importing keeps that deck's own show/hide choice rather than overriding it.
    The campaign itself arrives as a draft either way.

    Args:
        destination_schema (str): The schema to import the quests into.
        quest_import_ids (list): A list of quest import UUIDs to import.
        campaign_import_id (UUID): The import ID of the campaign to deactivate after import.

    Returns:
        TransferResult: The quests as they now exist on the destination deck, and the
            names of any prerequisites this deck does not have.

    Raises:
        LibraryTransferError: If a quest cannot be written to the destination deck, for
            instance because one of its names is already taken there.
    """
    with library_schema_context():
        # select_related/prefetch_related: snapshot_quest reads each quest's campaign and
        # its questions, which are a query each otherwise.
        quests = (
            Quest.objects.select_related('campaign')
            .prefetch_related('question_set')
            .filter(published=True, import_id__in=quest_import_ids)
        )
        snapshots = [snapshot_quest(quest) for quest in quests]

    with schema_context(destination_schema):
        # One transaction for the whole arrival: `write_quests` is atomic on its own, but
        # the campaign is put back into draft afterwards, and a failure there would
        # otherwise leave the quests imported under a published campaign. The view tells
        # the teacher nothing was added when an import fails, so that has to be true of
        # every write here, not just the quests.
        with transaction.atomic():
            existing_quests = Quest.objects.filter(import_id__in=quest_import_ids)
            local_visibility = {quest.import_id: quest.published for quest in existing_quests}

            imported = write_quests(
                [
                    (snapshot, local_visibility.get(snapshot['fields']['import_id'], False), None)
                    for snapshot in snapshots
                ],
                with_campaign=True,
            )

            category = Category.objects.filter(import_id=campaign_import_id).first()
            if category:
                category.published = False
                category.full_clean()
                category.save()

    return imported


def import_quest_to(*, destination_schema, quest_import_id):
    """
    Imports a single quest into the destination schema without importing its campaign.

    The quest arrives as a draft, so staff review it before students can see it.

    Args:
        destination_schema (str): The schema to import the quest into.
        quest_import_id (UUID): The import ID of the quest to import.

    Returns:
        TransferResult: The quest as it now exists on the destination deck, and the names
            of any prerequisites this deck does not have.

    Raises:
        Quest.DoesNotExist: If no *published* quest with the given import_id exists in
            the library. Content awaiting a Library admin's review is unpublished and
            must not travel to other decks (#1949), so it is filtered out here as well
            as in the view.
        LibraryTransferError: If the quest cannot be written to the destination deck,
            for instance because its name is already taken there.
    """
    with library_schema_context():
        quest = Quest.objects.get(import_id=quest_import_id, published=True)
        snapshot = snapshot_quest(quest)

    with schema_context(destination_schema):
        return write_quests([(snapshot, False, None)], with_campaign=False)
