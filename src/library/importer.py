from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest

from .utils import library_schema_context


def import_quests_to(*, destination_schema, quest_import_ids):
    """
    :param destination_schema: schema to import the quest to
    :param quest_import_ids: list of quest import ids
    """

    with library_schema_context():
        quests = Quest.objects.select_related('campaign').filter(visible_to_students=True, import_id__in=quest_import_ids)
        export_data = QuestResource().export(quests)

    dry_run = False
    with schema_context(destination_schema):
        res = QuestResource().import_data(export_data, dry_run=dry_run)

        object_ids = []
        for row in res.rows:
            if row.new_record:
                object_ids.append(row.object_id)
        # Set visible_to_students to False for imported quests
        # since the imported quests will be orphans
        Quest.objects.filter(pk__in=object_ids).update(visible_to_students=False)

    return res
