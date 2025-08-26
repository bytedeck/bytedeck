from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest, Category
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from datetime import date
from copy import deepcopy
from uuid import uuid4
from .utils import library_schema_context, get_library_conflicting_quests


def export_quest_to_library(*, source_schema, quest_import_id):
    """
    Exports a single quest from a given tenant schema into the shared library schema.

    The exported quest will not be automatically published in the library.

    Args:
        source_schema (str): The tenant schema where the quest currently resides.
        quest_import_id: The import ID (UUID) of the quest to export.

    Returns:
        ImportResult: The result of the import operation into the library schema.

    Raises:
        Quest.DoesNotExist: If the quest is not found in the source schema.
        ValidationError: If the import fails due to validation or integrity issues.
    """
    from django.core.exceptions import ObjectDoesNotExist

    with schema_context(source_schema):
        try:
            quest = Quest.objects.get(import_id=quest_import_id)
        except ObjectDoesNotExist as e:
            raise Quest.DoesNotExist(f"Quest with import_id={quest_import_id} not found in schema {source_schema}") from e
        export_data = QuestResource().export([quest])

    with library_schema_context():
        try:
            result = QuestResource().import_data(
                export_data,
                dry_run=False,
                raise_errors=True,
                use_transactions=True,
            )
        except (ValidationError, IntegrityError) as e:
            # Raise a clearer validation error with context
            raise ValidationError(f"Failed to import quest to library schema: {e}") from e

        # Make sure the quest is unpublished in the library
        imported_quest = Quest.objects.get(import_id=quest.import_id)
        imported_quest.published = False
        imported_quest.full_clean()
        imported_quest.save()

    return result


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
        ImportResult: The result of the import operation into the library schema.

    Raises:
        Category.DoesNotExist: If the campaign is not found in the source schema.
        ValidationError: If no published quests exist for the campaign and
            `skip_import_ids` was not provided.
    """
    with schema_context(source_schema):
        category = Category.objects.get(import_id=campaign_import_id)
        quests = Quest.objects.filter(published=True, campaign=category)

        # filter out conflicts (they'll be cloned and exported later)
        if skip_import_ids:
            quests = quests.exclude(import_id__in=skip_import_ids)

        if not quests.exists() and not skip_import_ids:
            raise ValidationError("Cannot export a campaign without any published quests.")
        export_data = QuestResource().export(quests)

    # Prepare visibility map for library: all quests unpublished
    exported_visibility_map = {str(q.import_id): False for q in quests}

    with library_schema_context():
        try:
            result = QuestResource().import_data(
                export_data,
                dry_run=False,
                raise_errors=True,
                use_transactions=True,
                import_campaign=True,
                local_visibility_map=exported_visibility_map,
            )
        except (ValidationError, IntegrityError) as e:
            # Raise a clearer validation error with context
            raise ValidationError(f"Failed to import campaign to library schema: {e}") from e

        # Explicitly unpublish imported campaign
        imported_category = Category.objects.filter(import_id=campaign_import_id).first()
        if imported_category:
            imported_category.published = False
            imported_category.full_clean()
            imported_category.save(update_fields=['published'])

    return result


def export_campaign_and_copy_quests(source_schema, campaign_import_id):
    """
    Export a campaign and its quests to the library, cloning conflicts.

    Process:
      - Detect quests in the target library that share an import_id with local quests.
      - Export only the non-conflicting quests (unpublished) and the campaign.
      - Ensure the campaign exists in the library.
      - For each conflicting local quest, create a new unpublished copy in the
        library campaign with a fresh import_id and a suffixed name to avoid
        uniqueness issues.

    Args:
        source_schema (str): Tenant schema that contains the source campaign.
        campaign_import_id (UUID): Import ID of the campaign to export.

    Returns:
        Category: The library campaign instance.

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
    export_campaign_to_library(source_schema=source_schema,
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

        # Step 4: clone only the conflicting quests
        for local_quest in local_quests:
            if local_quest.import_id in library_conflicting_ids:
                clone = deepcopy(local_quest)
                clone.pk = None
                clone.import_id = uuid4()
                clone.campaign = library_campaign
                clone.published = False

                # make sure name fits max length
                max_len = Quest._meta.get_field("name").max_length or 50
                suffix = f" (Exported on {date.today()})"
                counter = 1
                while Quest.objects.filter(name=local_quest.name[:max_len - len(suffix)] + suffix).exists():
                    suffix = f"{suffix} #{counter}"
                    counter += 1
                clone.name = local_quest.name[:max_len - len(suffix)] + suffix

                clone.full_clean()
                clone.save()

        return library_campaign
