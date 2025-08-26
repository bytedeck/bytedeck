import functools

from django.apps import apps
from django_tenants.utils import schema_context


def get_library_schema_name():
    return apps.get_app_config('library').TENANT_NAME


def from_library_schema_first(request):
    """
    Function to check if the POST request contains `use_schema` data which will allow us to
    use the library schema for fetching campaigns or quest data
    """

    current_schema_name = request.tenant.schema_name
    use_schema_name = request.POST.get('use_schema')
    schema_name = use_schema_name if use_schema_name else current_schema_name

    force_schema_func = functools.partial(schema_context, schema_name)

    return force_schema_func()


library_schema_context = functools.partial(schema_context, get_library_schema_name())


def get_library_conflicting_quests(local_quests):
    """
    Given a set of local quests, return any quests in the library
    that share the same import_id (i.e., conflicts).

    Args:
        local_quests (Iterable[Quest]): Local quests to check.

    Returns:
        list[Quest]: List of conflicting Quest objects from the library.
    """
    from quest_manager.models import Quest
    quest_import_ids = [q.import_id for q in local_quests if q.import_id]

    with library_schema_context():
        conflicts = list(
            Quest.objects.all_including_archived()
            .filter(import_id__in=quest_import_ids)
            .values_list('import_id', flat=True)
        )

    return conflicts
