from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest, Category

from .utils import library_schema_context
from django.core.exceptions import ValidationError
from django.db import IntegrityError


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


def export_campaign_to_library(*, source_schema, campaign_import_id):
    """
    Exports a campaign (Category) and all its quests from the given tenant schema
    into the shared library schema.

    All exported quests and the campaign will be unpublished in the library by default.
    This ensures the shared library remains a neutral, reviewable repository.

    Args:
        source_schema (str): The tenant schema where the campaign currently resides.
        campaign_import_id (UUID): The import ID of the campaign to export.

    Returns:
        ImportResult: The result of the import operation into the library schema.

    Raises:
        Category.DoesNotExist: If the campaign is not found in the source schema.
        ValidationError: If no published quests exist for the campaign.
    """
    with schema_context(source_schema):
        category = Category.objects.get(import_id=campaign_import_id)
        quests = Quest.objects.filter(published=True, campaign=category)
        if not quests.exists():
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
