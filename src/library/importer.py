from datetime import date

from django.db import transaction
from django_tenants.utils import schema_context
from quest_manager.models import Quest, Category

from .transfer import _write_campaign, build_available_quest_name, snapshot_campaign, snapshot_quest, write_quests
from .utils import library_schema_context


def resolve_name_collisions(snapshots):
    """Give an arriving quest a name of its own when this deck already uses the one it has.

    `Quest.name` is unique per schema, so a quest whose name is already taken here cannot
    be written at all: the whole import fails, and for a campaign that means one clashing
    name costs every other quest in it. The names most likely to clash are exactly the ones
    a shared library exists to distribute, since two decks that both wrote a quest called
    "Welcome to ByteDeck" is the expected case rather than an exotic one (#2364, #2397).

    A quest this deck already holds under the same `import_id` is not a collision: that is
    the same quest arriving again, and it keeps its row (and its name) rather than being
    renamed alongside itself.

    Must be called from within the destination schema context.

    Args:
        snapshots (list[dict]): the quest snapshots about to be written.

    Returns:
        tuple[dict, list]: field overrides keyed by `import_id`, ready to hand to
        `write_quests`; and the renames as `(wanted_name, given_name)` pairs, in the order
        the quests were snapshotted, so the importer can be told what changed.
    """
    arriving_ids = {snapshot['fields']['import_id'] for snapshot in snapshots}
    taken_names = set(
        Quest.objects.all_including_archived()
        .exclude(import_id__in=arriving_ids)
        .values_list('name', flat=True)
    )
    suffix = f" (Imported on {date.today()})"

    overrides = {}
    renames = []
    for snapshot in snapshots:
        wanted = snapshot['fields']['name']
        if wanted not in taken_names:
            continue

        given = build_available_quest_name(wanted, taken_names, suffix)
        taken_names.add(given)
        overrides[snapshot['fields']['import_id']] = {'name': given}
        renames.append((wanted, given))

    return overrides, renames


def import_campaign_to(*, destination_schema, quest_import_ids, campaign_import_id, preserve_import_ids=()):
    """
    Imports the given campaign and all quests from the library schema into the given destination schema.

    Imported quests arrive as drafts, except where the destination deck already has the
    quest: re-importing keeps that deck's own show/hide choice rather than overriding it.
    The campaign itself arrives as a draft either way.

    A quest named in `preserve_import_ids` is not written: the deck keeps the version it
    already has, edits and all. It is still put into the arriving campaign, so the campaign
    is whole rather than missing a part, which is the decision recorded on #1845. That has a
    consequence the teacher has to be told about rather than protected from: the campaign
    arrives unpublished, and a quest in an unpublished campaign is hidden from students, so
    a preserved quest that was visible stops being visible until the campaign is published.

    Args:
        destination_schema (str): The schema to import the quests into.
        quest_import_ids (list): A list of quest import UUIDs to import.
        campaign_import_id (UUID): The import ID of the campaign to deactivate after import.
        preserve_import_ids (Iterable[UUID]): quests the deck already has and wants to keep
            as they are. Ignored when the deck does not actually have them.

    Returns:
        TransferResult: The quests as they now exist on the destination deck, the names of
            any prerequisites this deck does not have, and any quests renamed on the way in
            because this deck already used their name.

    Raises:
        LibraryTransferError: If a quest cannot be written to the destination deck.
    """
    preserve_import_ids = list(preserve_import_ids)

    with library_schema_context():
        # select_related/prefetch_related: snapshot_quest reads each quest's campaign and
        # its questions, which are a query each otherwise.
        quests = (
            Quest.objects.select_related('campaign')
            .prefetch_related('question_set')
            .filter(published=True, import_id__in=quest_import_ids)
            .exclude(import_id__in=preserve_import_ids)
        )
        snapshots = [snapshot_quest(quest) for quest in quests]
        # Taken here because the campaign row on the destination is normally created from
        # the arriving quests' snapshots. Preserve every quest and none arrive, so there
        # would be no campaign for the preserved ones to join.
        library_campaign = Category.objects.filter(import_id=campaign_import_id).first()
        campaign_snapshot = snapshot_campaign(library_campaign)

    with schema_context(destination_schema):
        # One transaction for the whole arrival: `write_quests` is atomic on its own, but
        # the campaign is put back into draft afterwards, and a failure there would
        # otherwise leave the quests imported under a published campaign. The view tells
        # the teacher nothing was added when an import fails, so that has to be true of
        # every write here, not just the quests.
        with transaction.atomic():
            existing_quests = Quest.objects.filter(import_id__in=quest_import_ids)
            local_visibility = {quest.import_id: quest.published for quest in existing_quests}
            overrides, renames = resolve_name_collisions(snapshots)

            imported = write_quests(
                [
                    (
                        snapshot,
                        local_visibility.get(snapshot['fields']['import_id'], False),
                        overrides.get(snapshot['fields']['import_id']),
                    )
                    for snapshot in snapshots
                ],
                with_campaign=True,
            )

            category = Category.objects.filter(import_id=campaign_import_id).first()
            if category is None and campaign_snapshot is not None:
                category = _write_campaign(campaign_snapshot)

            if category:
                category.published = False
                category.full_clean()
                category.save()

                # Saved one at a time rather than through a bulk update, so a quest moving
                # between campaigns raises the same signals it would if a teacher moved it
                # by hand: the quest map is rebuilt from campaigns.
                for quest in Quest.objects.filter(import_id__in=preserve_import_ids):
                    quest.campaign = category
                    quest.full_clean(exclude=['campaign'])
                    quest.save()

    return imported._replace(renamed_quests=renames)


def import_quest_to(*, destination_schema, quest_import_id):
    """
    Imports a single quest into the destination schema without importing its campaign.

    The quest arrives as a draft, so staff review it before students can see it.

    Args:
        destination_schema (str): The schema to import the quest into.
        quest_import_id (UUID): The import ID of the quest to import.

    Returns:
        TransferResult: The quest as it now exists on the destination deck, the names of
            any prerequisites this deck does not have, and the rename if this deck already
            used the quest's name.

    Raises:
        Quest.DoesNotExist: If no *published* quest with the given import_id exists in
            the library. Content awaiting a Library admin's review is unpublished and
            must not travel to other decks (#1949), so it is filtered out here as well
            as in the view.
        LibraryTransferError: If the quest cannot be written to the destination deck.
    """
    with library_schema_context():
        quest = Quest.objects.get(import_id=quest_import_id, published=True)
        snapshot = snapshot_quest(quest)

    with schema_context(destination_schema):
        overrides, renames = resolve_name_collisions([snapshot])
        imported = write_quests([(snapshot, False, overrides.get(quest_import_id))], with_campaign=False)

        return imported._replace(renamed_quests=renames)
