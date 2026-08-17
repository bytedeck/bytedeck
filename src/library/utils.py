import functools

from django.apps import apps
from django.db.models import prefetch_related_objects
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


def library_listable_quests():
    """The quests the Library offers to other decks.

    A quest carries `date_available` and `date_expired` across the schema boundary, so in
    the Library those dates describe the timetable of the deck that shared it. The Library
    is a catalogue rather than a feed of what a student can start right now, so it lists by
    what it holds: published, not archived, and not sitting behind an unpublished campaign.
    That matches how the Campaigns tab already counts importable quests, so the two tabs
    agree on what the Library contains.

    Must be called from within the library schema context.

    Returns:
        QuerySet[Quest]: the listable quests, unordered.
    """
    from quest_manager.models import Quest

    return Quest.objects.get_queryset().published().active_or_no_campaign()


def load_library_quests_for_render(quests):
    """Read everything a Library quest's template will ask for, while the schema is right.

    Library views select their quests inside `library_schema_context()` and render after it
    has closed. Anything still lazy at that point (a related manager, a queryset, an
    unfetched foreign key) is evaluated by the template engine, by which time the connection
    is back on the viewer's own deck: it reads *this* deck's tables using the Library row's
    primary key, and the page shows the viewer their own data as though it were the shared
    content's. Nothing raises, so the only sign is that the wrong thing is on the screen
    (#2369, #2163).

    Loading it here rather than at each call site means the fix is one line per view instead
    of a prefetch per relation that the next template change can silently outgrow.

    Rendering the page *on* the Library schema is not the alternative it looks like: the
    page is mostly the viewer's own deck (their profile, their SiteConfig, their navbar),
    none of which exists in the Library schema.

    Must be called from within the library schema context, on an already-evaluated list.

    Args:
        quests (list[Quest]): the quests about to be rendered. A list, not a queryset:
            `prefetch_related_objects` needs the rows to exist.

    Returns:
        list[Quest]: the same list, with `tags`, `question_set` and `campaign` populated.
    """
    prefetch_related_objects(quests, 'tags', 'question_set', 'campaign')

    return quests


def get_colliding_quest_names(library_quests):
    """The names among `library_quests` that a different quest on this deck already uses.

    A name clash is what the importing teacher cannot see for themselves: the Library page
    shows what is on offer, not what is already on their own deck, so without this the
    first they hear of it is after clicking Import. The import handles the clash by
    renaming the arriving copy, and naming the clash up front is what makes that a choice
    rather than a surprise (#2364, #2397).

    Matching is on name and *not* import_id: a quest this deck already holds under the same
    import_id is the same quest arriving again, which is an overwrite rather than a clash.

    Must be called from within the destination (local) schema context.

    Args:
        library_quests (Iterable[Quest]): the quests being offered for import, read from
            the Library schema.

    Returns:
        list[str]: the clashing names, sorted, empty when nothing on this deck collides.
    """
    from quest_manager.models import Quest

    wanted_names = [quest.name for quest in library_quests]
    arriving_ids = [quest.import_id for quest in library_quests]

    return sorted(
        Quest.objects.all_including_archived()
        .filter(name__in=wanted_names)
        .exclude(import_id__in=arriving_ids)
        .values_list('name', flat=True)
    )


def get_library_conflicting_quests(local_quests):
    """
    Given a list of local Quest objects, return the import_ids of any quests in
    the library that share an import_id with them (i.e., conflicts).

    Args:
        local_quests (List[Quest]): Local quests to check.

    Returns:
        list[UUID]: The import_ids that already exist in the library. Callers use
            these to tell which of the local quests would collide, so this is a
            list of ids rather than of the library's Quest objects.
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
