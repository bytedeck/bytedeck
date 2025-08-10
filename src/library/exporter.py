from django_tenants.utils import schema_context
from quest_manager.admin import QuestResource
from quest_manager.models import Quest

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
