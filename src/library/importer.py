from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest, Category

from .utils import library_schema_context


def import_quests_to(*, destination_schema, quest_import_ids):
    """
    Imports one or more quests from the library schema into the given destination schema.

    Automatically sets imported quests to not be visible to students, and deactivates
    the associated campaign if one is present.

    Args:
        destination_schema (str): The schema to import the quests into.
        quest_import_ids (list): A list of quest import UUIDs to import.
    """

    with library_schema_context():
        quests = Quest.objects.select_related('campaign').filter(published=True, import_id__in=quest_import_ids)
        export_data = QuestResource().export(quests)

        # Grab the campaign's import_id from the first quest (if present)
        campaign_import_id = None
        first_quest = quests.first()
        if first_quest and first_quest.campaign:
            campaign_import_id = first_quest.campaign.import_id

    dry_run = False
    with schema_context(destination_schema):
        res = QuestResource().import_data(export_data, dry_run=dry_run)

        object_ids = []
        for row in res.rows:
            if row.new_record:
                object_ids.append(row.object_id)
        # Set published to False for imported quests
        # since the imported quests will be orphans
        Quest.objects.filter(pk__in=object_ids).update(published=False)

        # Deactivate related campaign if one exists
        campaign = Category.objects.filter(import_id=campaign_import_id).first()
        if campaign:
            campaign.active = False
            campaign.full_clean()
            campaign.save()

    return res
