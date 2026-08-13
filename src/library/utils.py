import functools

from django.apps import apps
from django_tenants.utils import schema_context


def get_library_schema_name():
    return apps.get_app_config('library').TENANT_NAME


# POST flag the front end sets to ask for a preview out of the shared Library
# instead of the caller's own deck. It is a boolean: the schema name is never
# taken from the request (see `library_schema_if_requested`).
LIBRARY_SCHEMA_POST_FLAG = 'use_library_schema'

# Values jQuery / a plain form can send for a "true" boolean.
_TRUTHY_POST_VALUES = frozenset(['1', 'true', 'True', 'on', 'yes'])


def is_library_schema_requested(request):
    """Whether this request asked to be served out of the shared Library schema.

    Args:
        request (HttpRequest): the current request.

    Returns:
        bool: True if the request carries the Library flag with a truthy value.
    """
    return request.POST.get(LIBRARY_SCHEMA_POST_FLAG) in _TRUTHY_POST_VALUES


def library_schema_if_requested(request):
    """Return a schema context for this request: the Library, or the caller's own deck.

    The request only gets to ask a yes/no question. The schema name itself is
    resolved here from `get_library_schema_name()`, never read off the request:
    a request that could name its own schema would let any authenticated user
    read another deck's content just by POSTing that deck's schema name, since
    schema names are public (they are the decks' subdomains).

    Args:
        request (HttpRequest): the current request.

    Returns:
        context manager: switches the connection to the resolved schema.
    """
    schema_name = get_library_schema_name() if is_library_schema_requested(request) else request.tenant.schema_name

    return schema_context(schema_name)


library_schema_context = functools.partial(schema_context, get_library_schema_name())


def get_library_conflicting_quests(local_quests):
    """
    Given a list of local Quest objects, return any quests in the library
    that share the same import_id (i.e., conflicts).

    Args:
        local_quests (List[Quest]): Local quests to check.

    Returns:
        list[Quest]: List of conflicting Quest objects from the library.
    """
    from quest_manager.models import Quest
    quest_import_ids = [q.import_id for q in local_quests]

    with library_schema_context():
        conflicts = list(
            Quest.objects.all_including_archived()
            .filter(import_id__in=quest_import_ids)
            .values_list('import_id', flat=True)
        )

    return conflicts
