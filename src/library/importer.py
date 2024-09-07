from django_tenants.utils import schema_context
from library.utils import get_library_schema_name
from quest_manager.admin import QuestResource
from quest_manager.models import Quest


def import_quests_to(*, destination_schema, quest_import_ids, source_schema=None):
    """
    :param destination_schema: schema to import the quest to
    :param quest_import_ids: list of quest import ids
    :param source_schema: Optional. The source where to import the quest import ids
    """

    if source_schema is None:
        source_schema = get_library_schema_name()

    with schema_context(source_schema):
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
