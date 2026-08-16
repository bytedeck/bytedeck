from datetime import date
from uuid import uuid4

from django_tenants.utils import schema_context
from quest_manager.models import Quest, Category
from django.core.exceptions import ValidationError

from .transfer import TransferResult, snapshot_quest, write_quests
from .utils import library_schema_context, get_library_conflicting_quests


def build_library_clone_name(local_name, taken_names):
    """Return a name for a clone of `local_name` that is free in the Library.

    Quest names are unique per schema and capped at the model's max_length, so a
    clone of a quest whose original is already in the Library needs a name of its
    own. Falls back to numbered suffixes when the dated one is also taken.

    Args:
        local_name (str): the source quest's name.
        taken_names (set[str]): every name already spoken for in the Library.
            Must include archived quests: they still hold their name against the
            unique constraint even though the default manager hides them.

    Returns:
        str: a name not in `taken_names`, within the field's max_length.
    """
    max_len = Quest._meta.get_field('name').max_length or 50
    base_suffix = f" (Exported on {date.today()})"

    candidate = local_name[:max_len - len(base_suffix)] + base_suffix
    counter = 1
    while candidate in taken_names:
        full_suffix = f"{base_suffix} #{counter}"
        candidate = local_name[:max_len - len(full_suffix)] + full_suffix
        counter += 1

    return candidate


def clone_quests_into_library(*, source_schema, quests):
    """Copy quests into the Library as fresh entries, leaving the originals alone.

    Used when a campaign is shared but some of its quests are already in the
    Library under the same `import_id`: those get a new copy rather than
    overwriting what is there.

    Each copy is written with a fresh `import_id` and a name of its own, so it lands
    beside the Library's existing version instead of replacing it. Everything else
    travels exactly as a normal push does.

    Args:
        source_schema (str): the tenant schema holding the quests being copied.
        quests (list[Quest]): quests loaded from `source_schema`.

    Returns:
        TransferResult: the copies now in the Library, empty when there was nothing to
        copy, plus any prerequisites that could not travel with them.

    Raises:
        LibraryTransferError: if a copy cannot be written to the Library.
    """
    if not quests:
        return TransferResult(quests=[], unmet_prereqs=[])

    with schema_context(source_schema):
        snapshots = [snapshot_quest(quest) for quest in quests]

    with library_schema_context():
        # Archived quests count: the unique constraint does not care that the
        # default manager hides them.
        taken_names = set(Quest.objects.all_including_archived().values_list('name', flat=True))

        writes = []
        for snapshot in snapshots:
            name = build_library_clone_name(snapshot['fields']['name'], taken_names)
            taken_names.add(name)
            writes.append((snapshot, False, {'import_id': uuid4(), 'name': name}))

        return write_quests(writes, with_campaign=True)


def export_quest_to_library(*, source_schema, quest_import_id):
    """
    Exports a single quest from a given tenant schema into the shared library schema.

    The exported quest will not be automatically published in the library.

    Args:
        source_schema (str): The tenant schema where the quest currently resides.
        quest_import_id: The import ID (UUID) of the quest to export.

    Returns:
        TransferResult: The quest as it now exists in the library schema, and the names of
            any prerequisites that could not travel with it.

    Raises:
        Quest.DoesNotExist: If the quest is not found in the source schema.
        LibraryTransferError: If the quest cannot be written to the library schema.
    """
    from django.core.exceptions import ObjectDoesNotExist

    with schema_context(source_schema):
        try:
            quest = Quest.objects.get(import_id=quest_import_id)
        except ObjectDoesNotExist as e:
            raise Quest.DoesNotExist(f"Quest with import_id={quest_import_id} not found in schema {source_schema}") from e
        snapshot = snapshot_quest(quest)

    with library_schema_context():
        return write_quests([(snapshot, False, None)], with_campaign=False)


def export_campaign_to_library(*, source_schema, campaign_import_id, skip_import_ids=None):
    """
    Exports a campaign (Category) and its published quests from the given tenant
    schema into the shared library schema. By default, all published quests in
    the campaign are exported. If `skip_import_ids` is provided, any quests whose
    `import_id` is in that set are excluded (e.g., when you plan to clone
    conflicts separately).

    All exported quests and the campaign will be unpublished in the library by default.
    This ensures the shared library remains a neutral, reviewable repository.

    Args:
        source_schema (str): The tenant schema where the campaign currently resides.
        campaign_import_id (UUID): The import ID of the campaign to export.
        skip_import_ids (Iterable[UUID] | None): Optional set of quest import_ids
            to exclude from the export. When provided, the export will proceed
            even if all quests are skipped

    Returns:
        TransferResult: The quests as they now exist in the library schema, and the names
            of any prerequisites that could not travel with them.

    Raises:
        Category.DoesNotExist: If the campaign is not found in the source schema.
        ValidationError: If no published quests exist for the campaign and
            `skip_import_ids` was not provided.
        LibraryTransferError: If a quest cannot be written to the library schema.
    """
    with schema_context(source_schema):
        category = Category.objects.get(import_id=campaign_import_id)
        # select_related: snapshot_quest reads quest.campaign for every row.
        quests = Quest.objects.select_related('campaign').filter(published=True, campaign=category)

        # filter out conflicts (they'll be cloned and exported later)
        if skip_import_ids:
            quests = quests.exclude(import_id__in=skip_import_ids)

        if not quests.exists() and not skip_import_ids:
            raise ValidationError("Cannot export a campaign without any published quests.")
        snapshots = [snapshot_quest(quest) for quest in quests]

    with library_schema_context():
        exported = write_quests([(snapshot, False, None) for snapshot in snapshots], with_campaign=True)

        # The campaign is only created unpublished; force it back to draft in case the
        # Library already holds a published copy under this import_id.
        imported_category = Category.objects.filter(import_id=campaign_import_id).first()
        if imported_category:
            imported_category.published = False
            imported_category.full_clean()
            imported_category.save(update_fields=['published'])

    return exported


def export_campaign_and_copy_quests(source_schema, campaign_import_id):
    """
    Export a campaign and its quests to the library, cloning conflicts.

    Process:
      - Detect quests in the target library that share an import_id with local quests.
      - Export only the non-conflicting quests (unpublished) and the campaign.
      - Ensure the campaign exists in the library.
      - Copy each conflicting local quest into the library campaign as a new
        unpublished entry with a fresh import_id and a name of its own, leaving
        the library's existing version untouched.

    Args:
        source_schema (str): Tenant schema that contains the source campaign.
        campaign_import_id (UUID): Import ID of the campaign to export.

    Returns:
        TransferResult: The quests as they now exist in the library, and the names of any
            prerequisites that could not travel with them.

    Raises:
        Category.DoesNotExist: If the campaign is not found in the source schema.
    """

    # Step 1: get local campaign and quests first (in source schema)
    with schema_context(source_schema):
        local_campaign = Category.objects.get(import_id=campaign_import_id)
        local_quests = list(local_campaign.current_quests())

    # detect which local quests already exist in the library before the export happens
    library_conflicting_ids = get_library_conflicting_quests(local_quests)

    # Step 2: export campaign + quests normally
    exported = export_campaign_to_library(source_schema=source_schema,
                                          campaign_import_id=campaign_import_id,
                                          skip_import_ids=library_conflicting_ids
                                          )

    # Step 3: ensure the campaign exists in the library
    with library_schema_context():
        existing = Category.objects.filter(import_id=campaign_import_id).first()
        if existing:
            library_campaign = existing
        else:
            library_campaign = Category(
                import_id=campaign_import_id,
                title=local_campaign.title,
                icon=local_campaign.icon,
                short_description=local_campaign.short_description,
                published=False,
            )
            library_campaign.full_clean()
            library_campaign.save()

    # Step 4: copy the conflicting quests in alongside the campaign. They carry
    # the campaign in their snapshot, so they attach to the campaign ensured above.
    conflicting_quests = [q for q in local_quests if q.import_id in library_conflicting_ids]
    cloned = clone_quests_into_library(source_schema=source_schema, quests=conflicting_quests)

    return TransferResult(
        quests=exported.quests + cloned.quests,
        unmet_prereqs=sorted(set(exported.unmet_prereqs) | set(cloned.unmet_prereqs)),
    )
