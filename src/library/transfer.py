"""Copying quests and campaigns between a deck's schema and the Shared Library.

Sharing content between decks is a copy from one Postgres schema to another, in the same
database on the same connection. This module does that copy directly: it reads the source
objects in one schema context and writes them in the other, resolving cross-schema
references by the keys that mean the same thing everywhere (`import_id` for content, tag
names for tags).

Nothing here is serialized to a file format on the way. Structure stays structured: a
campaign travels as a campaign, and a prerequisite as the id of the thing it points at.
The previous approach round-tripped every quest through a tablib `Dataset` (a table of
scalar cells, built for CSV and XLSX), which cost real fidelity, because anything that is
not a scalar had to be flattened into one: the campaign became four parallel columns, and
the prerequisite graph became one `&`-joined string of ids (#2445).

Two rules hold everywhere below:

* **Schema context is the caller's job at the boundary, and explicit inside.** Every
  function that touches the database says which schema it must run in. Reading and writing
  are separated by a snapshot (see `snapshot_quest`) precisely so that no queryset is ever
  evaluated lazily in the wrong schema.
* **Failures are raised, not reported.** A copy either happens or raises
  `LibraryTransferError`. The mechanism this replaced returned a result object carrying
  row-level errors that every caller discarded, so a failed import looked exactly like a
  successful one (#2397, #2364).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from prerequisites.models import Prereq
from quest_manager.models import Category, Quest


class LibraryTransferError(Exception):
    """A quest or campaign could not be copied between schemas.

    Raised instead of returning a result object that callers have to remember to inspect.
    Carries the human-readable reason, so a view can put it in front of the user.
    """


# Quest fields that do not cross the schema boundary, and why. Everything else on the
# model travels, so a field added to Quest travels by default. Whether that is right for
# a given field is a decision someone has to make: the field inventory tests in
# `test_transfer_contract.py` fail until the new field is classified there.
QUEST_FIELDS_NOT_COPIED = {
    'id': 'Primary key. The destination assigns its own.',
    'editor': 'FK to a user on the source deck, so the pk means someone else here.',
    'specific_teacher_to_notify': 'FK to a user on the source deck, same reason as editor.',
    'common_data': 'CommonData has no import_id, so there is no cross-schema key for it (#2398).',
    'campaign': 'Copied as an object rather than an FK, since the pk differs per schema.',
    'published': 'Set by the caller: content arrives as a draft for review.',
    'datetime_created': 'auto_now_add. The destination stamps its own creation time.',
    'datetime_last_edit': 'auto_now. Always the time of the copy.',
}

# Campaign fields that do not cross, same idea.
CAMPAIGN_FIELDS_NOT_COPIED = {
    'id': 'Primary key. The destination assigns its own.',
    'published': 'Set by the caller: content arrives as a draft for review.',
    'map_order': 'Quest-map placement, which is relative to the deck it was arranged on (#2396).',
}


def _copied_field_names(model, not_copied):
    """The concrete fields of `model` that travel between schemas.

    Args:
        model (type[Model]): the model whose fields to list.
        not_copied (dict[str, str]): field names that stay behind, mapped to the reason.

    Returns:
        list[str]: the field names to copy, in the model's own order.
    """
    return [f.name for f in model._meta.concrete_fields if f.name not in not_copied]


def _read_field(instance, name):
    """Read one field in a form that can be written into another schema.

    File and image fields are copied by their stored path rather than as a file object:
    decks share one media namespace, so the path resolves on the destination and the
    bytes never need to move.

    Args:
        instance (Model): the object being copied.
        name (str): the field to read.

    Returns:
        object: the value to write on the far side.
    """
    value = getattr(instance, name)

    return value.name if hasattr(value, 'name') and hasattr(value, 'storage') else value


def snapshot_campaign(campaign):
    """Take a portable copy of a campaign's travelling state.

    Must be called from within the source schema context.

    Args:
        campaign (Category | None): the campaign to snapshot, or None.

    Returns:
        dict | None: the campaign's copied field values, or None when there is no campaign.
    """
    if campaign is None:
        return None

    return {name: _read_field(campaign, name) for name in _copied_field_names(Category, CAMPAIGN_FIELDS_NOT_COPIED)}


def snapshot_quest(quest):
    """Take a portable copy of everything a quest carries to another deck.

    Reads eagerly (tags and prerequisites included) so the result can cross a schema
    switch safely: a lazy queryset evaluated after the switch would silently read the
    wrong schema.

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest to snapshot.

    Returns:
        dict: with keys `fields` (the quest's own values), `tags` (tag names), `campaign`
        (a campaign snapshot or None) and `prereq_import_ids` (the import_ids of the
        quests and badges it requires).
    """
    return {
        'fields': {name: _read_field(quest, name) for name in _copied_field_names(Quest, QUEST_FIELDS_NOT_COPIED)},
        # By name, not by primary key: tag rows are per-schema, so a pk means a different
        # tag (or none) on the far side (#1792).
        'tags': sorted(quest.tags.names()),
        'campaign': snapshot_campaign(quest.campaign),
        'prereq_import_ids': _snapshot_prereq_import_ids(quest),
    }


def _snapshot_prereq_import_ids(quest):
    """The import_ids of the quests and badges this quest requires.

    Only prerequisites pointing at content that carries an `import_id` can travel, since
    that is the only identifier shared across schemas. A prerequisite whose target is not
    copied alongside the quest cannot be rebuilt on the far side (#2399).

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest whose prerequisites to read.

    Returns:
        list[UUID]: the import_ids of the prerequisite objects.
    """
    import_ids = []
    for prereq in quest.prereqs():
        target = prereq.get_prereq()
        target_import_id = getattr(target, 'import_id', None)
        if target_import_id is not None:
            import_ids.append(target_import_id)

    return import_ids


def _write_campaign(snapshot):
    """Find or create the destination's copy of a campaign.

    Matched by `import_id` first, then by title, so a deck that already arranged this
    campaign keeps the one it has rather than gaining a second copy of it. A campaign
    created here arrives unpublished, like the quests inside it.

    Must be called from within the destination schema context.

    Args:
        snapshot (dict): a campaign snapshot from `snapshot_campaign`.

    Returns:
        Category: the destination's campaign.
    """
    existing = Category.objects.filter(import_id=snapshot['import_id']).first()
    if existing is None:
        existing = Category.objects.filter(title=snapshot['title']).first()
    if existing is not None:
        return existing

    campaign = Category(published=False, **snapshot)
    campaign.full_clean()
    campaign.save()

    return campaign


def _write_prereqs(quest, prereq_import_ids):
    """Rebuild the prerequisites whose targets exist on this deck.

    A prerequisite can only point at a row that is actually here, so one whose target was
    not copied along with the quest is dropped. That is the loss #2399 describes; it is
    unchanged by this module, which can only link what the destination holds.

    Must be called from within the destination schema context.

    Args:
        quest (Quest): the freshly written quest.
        prereq_import_ids (list[UUID]): import_ids of the required quests and badges.
    """
    from badges.models import Badge

    already_required = {p.get_prereq() for p in quest.prereqs()}

    for import_id in prereq_import_ids:
        target = Quest.objects.all_including_archived().filter(import_id=import_id).first()
        if target is None:
            target = Badge.objects.filter(import_id=import_id).first()

        if target is not None and target not in already_required:
            Prereq.add_simple_prereq(quest, target)
            already_required.add(target)


def write_quests(writes, *, with_campaign):
    """Write several snapshotted quests into the current schema, then link them up.

    Prerequisites are linked in a second pass, once every quest in the batch exists. A
    prerequisite can only point at a row that is already there, so linking as each quest
    is written would drop any prerequisite pointing at a quest later in the batch, and
    which quests survived would depend on the order they happened to be written in.

    Must be called from within the destination schema context.

    Args:
        writes (list[tuple[dict, bool, dict | None]]): one `(snapshot, published,
            field_overrides)` triple per quest. See `write_quest` for what each means.
        with_campaign (bool): whether to attach (and if needed create) each quest's
            campaign.

    Returns:
        list[Quest]: the written quests, in the order given.

    Raises:
        LibraryTransferError: if any quest cannot be written.
    """
    # All of the batch or none of it: a half-written campaign would leave the deck holding
    # some quests of a set whose prerequisites reference the ones that never arrived.
    with transaction.atomic():
        written = [
            _write_quest_row(snapshot, published=published, with_campaign=with_campaign, field_overrides=overrides)
            for snapshot, published, overrides in writes
        ]

        for (snapshot, _, _), quest in zip(writes, written):
            _write_prereqs(quest, snapshot['prereq_import_ids'])

    return written


def write_quest(snapshot, *, published, with_campaign, field_overrides=None):
    """Write one snapshotted quest into the current schema.

    Must be called from within the destination schema context.

    Args:
        snapshot (dict): a quest snapshot from `snapshot_quest`.
        published (bool): the published state to give the written quest.
        with_campaign (bool): whether to attach (and if needed create) the campaign. A
            quest imported on its own does not drag a campaign onto the deck with it.
        field_overrides (dict | None): field values to replace on the way in, used by the
            conflict-copy path to give a copy its own `import_id` and name.

    Returns:
        Quest: the written quest.

    Raises:
        LibraryTransferError: if the quest cannot be written, most often because its name
            is already taken by a different quest on the destination deck.
    """
    return write_quests([(snapshot, published, field_overrides)], with_campaign=with_campaign)[0]


def _write_quest_row(snapshot, *, published, with_campaign, field_overrides=None):
    """Write a quest's own fields, campaign and tags, leaving prerequisites to the caller.

    An existing row with the same `import_id` is updated rather than duplicated, which is
    what makes re-sharing a quest refresh the Library's copy instead of adding a second.

    Must be called from within the destination schema context.

    Args:
        snapshot (dict): a quest snapshot from `snapshot_quest`.
        published (bool): the published state to give the written quest.
        with_campaign (bool): whether to attach (and if needed create) the campaign.
        field_overrides (dict | None): field values to replace on the way in.

    Returns:
        Quest: the written quest, without its prerequisites yet.

    Raises:
        LibraryTransferError: if the quest cannot be written.
    """
    fields = dict(snapshot['fields'], **(field_overrides or {}))
    import_id = fields['import_id']

    quest = Quest.objects.all_including_archived().filter(import_id=import_id).first() or Quest(import_id=import_id)
    for name, value in fields.items():
        setattr(quest, name, value)
    quest.published = published

    if with_campaign and snapshot['campaign'] is not None:
        quest.campaign = _write_campaign(snapshot['campaign'])

    try:
        with transaction.atomic():
            quest.full_clean(exclude=['campaign'])
            quest.save()
    except ValidationError as error:
        raise LibraryTransferError(f"'{fields['name']}' could not be copied: {_describe(error)}") from error
    except IntegrityError as error:
        raise LibraryTransferError(f"'{fields['name']}' could not be copied: {error}") from error

    quest.tags.set(snapshot['tags'])

    return quest


def _describe(error):
    """Render a ValidationError as one readable sentence.

    Args:
        error (ValidationError): the error raised by `full_clean`.

    Returns:
        str: the messages, joined, without Django's dict-and-list punctuation.
    """
    if hasattr(error, 'message_dict'):
        return '; '.join(f"{field}: {' '.join(messages)}" for field, messages in error.message_dict.items())

    return ' '.join(error.messages)
