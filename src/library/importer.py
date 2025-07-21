from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest, Category

from .utils import library_schema_context


def import_campaign_to(*, destination_schema, quest_import_ids, campaign_import_id):
    """
    Imports the given campaign and all quests from the library schema into the given destination schema.

    Automatically sets imported quests to not published,
    and deactivates the associated campaign if one is present.

    Args:
        destination_schema (str): The schema to import the quests into.
        quest_import_ids (list): A list of quest import UUIDs to import.
        campaign_import_id (UUID): The import ID of the campaign to deactivate after import.
    """

    with library_schema_context():
        quests = Quest.objects.select_related('campaign').filter(published=True, import_id__in=quest_import_ids)
        export_data = QuestResource().export(quests)

    dry_run = False
    with schema_context(destination_schema):

        existing_quests = Quest.objects.filter(import_id__in=quest_import_ids)
        local_visibility_map = {str(q.import_id): q.published for q in existing_quests}

        # Explicitly import the campaign as well
        result = QuestResource().import_data(export_data, dry_run=dry_run, import_campaign=True, local_visibility_map=local_visibility_map)

        category = Category.objects.filter(import_id=campaign_import_id).first()
        if category:
            category.active = False
            category.full_clean()
            category.save()

    return result


def import_quest_to(*, destination_schema, quest_import_id):
    """
    Imports a single quest into the destination schema without importing its campaign.

    Automatically sets imported quest to not published

    Args:
        destination_schema (str): The schema to import the quest into.
        quest_import_id (UUID): The import ID of the quest to import.

    Returns:
        ImportResult: The result of the import operation, including row-level status info.

    Raises:
        ValueError: If the quest with the given import_id does not exist in the source schema
                    or cannot be found in the destination schema after import.
    """
    with library_schema_context():
        quest = Quest.objects.get(import_id=quest_import_id)

        export_data = QuestResource().export([quest])

    with schema_context(destination_schema):
        result = QuestResource().import_data(
            export_data,
            dry_run=False,
            raise_errors=True,
            use_transactions=True,
        )

        imported_quest = Quest.objects.get(import_id=quest_import_id)
        imported_quest.published = False
        imported_quest.full_clean()
        imported_quest.save()

    return result
