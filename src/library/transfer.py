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

from typing import NamedTuple

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from prerequisites.models import Prereq
from quest_manager.models import Category, Quest
from questions.models import Question

from .models import IsLibraryContentMixin


class TransferResult(NamedTuple):
    """What a copy produced, what it could not bring with it, and what it had to change.

    The loss fields are the reason this is a result rather than a bare list of quests.
    Content shared to the Library is meant to be a self-contained package, so anything the
    copy could not carry is the *sharer's* business: they are the one who can widen what
    they share, or decide the gap is fine. The views turn these into a warning on the push.

    `unmet_prereqs` names gating that did not travel, which fails open: the copy in the
    Library ends up less gated than its author wrote. `skipped_quests` names quests that
    were left out of a shared campaign altogether. `dropped_common_data` names the shared
    General Info blocks the copy arrives without.

    `renamed_quests` is the odd one out: nothing was lost, but a name was changed to get
    the copy in, so it is reported to whoever is standing in front of it (#2364).
    """

    quests: list
    unmet_prereqs: list
    skipped_quests: list = ()
    dropped_common_data: list = ()
    renamed_quests: list = ()


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

# Submission-question fields that do not cross, same idea.
QUESTION_FIELDS_NOT_COPIED = {
    'id': 'Primary key. The destination assigns its own.',
    'quest': 'Set to the quest being written, whose pk differs per schema.',
    'datetime_created': 'auto_now_add. The destination stamps its own creation time.',
    'datetime_last_edit': 'auto_now. Always the time of the copy.',
}


def build_available_quest_name(name, taken_names, suffix):
    """Return a version of `name` that no quest in the destination schema is using.

    `Quest.name` is unique per schema, so a copy whose name is already spoken for cannot be
    written at all. Both directions of the transfer hit this: pushing a second copy of a
    quest that is already in the Library, and pulling a quest onto a deck that happens to
    have written its own quest of the same name. Both answer it the same way, by giving the
    copy a name of its own and saying so, rather than refusing the transfer.

    Args:
        name (str): the name the copy would like to keep.
        taken_names (set[str]): every name already spoken for in the destination schema.
            Must include archived quests: they still hold their name against the unique
            constraint even though the default manager hides them.
        suffix (str): what to append to distinguish the copy, e.g. " (Imported on
            2026-08-17)". Numbered when even the suffixed name is taken.

    Returns:
        str: a name not in `taken_names`, truncated to fit the field's max_length.
    """
    max_len = Quest._meta.get_field('name').max_length or 50

    candidate = name[:max_len - len(suffix)] + suffix
    counter = 1
    while candidate in taken_names:
        numbered = f"{suffix} #{counter}"
        candidate = name[:max_len - len(numbered)] + numbered
        counter += 1

    return candidate


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
        (a campaign snapshot or None), `prereqs` (the shareable things it requires, each as
        an import_id and a name), `questions` (its submission questions) and
        `common_data_title` (the General Info block it uses, which does not travel).
    """
    return {
        'fields': {name: _read_field(quest, name) for name in _copied_field_names(Quest, QUEST_FIELDS_NOT_COPIED)},
        # By name, not by primary key: tag rows are per-schema, so a pk means a different
        # tag (or none) on the far side (#1792).
        'tags': sorted(quest.tags.names()),
        'campaign': snapshot_campaign(quest.campaign),
        'prereqs': _snapshot_prereqs(quest),
        'questions': _snapshot_questions(quest),
        # Not copied (CommonData has no import_id to match it across schemas), but the
        # title travels so the sharer can be told the block stays behind (#2398).
        'common_data_title': quest.common_data.title if quest.common_data else None,
    }


def _snapshot_questions(quest):
    """The submission questions a quest asks, in the order the student answers them.

    A question is part of the quest's content, not of the deck it was written on: a quest
    whose instructions say "answer the questions below" is a different quest without them,
    so they travel with it (#2162). They have no identity of their own to travel under, so
    they ride inside the quest's snapshot and are matched on the far side by ordinal.

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest whose questions to read.

    Returns:
        list[dict]: one dict of copied field values per question, ordered by ordinal.
    """
    copied = _copied_field_names(Question, QUESTION_FIELDS_NOT_COPIED)

    return [{name: _read_field(question, name) for name in copied} for question in quest.question_set.all()]


def _snapshot_prereqs(quest):
    """The shareable prerequisites of a quest, as portable ids with readable names.

    A prerequisite is a generic foreign key, so it can point at any prerequisite model.
    Only those marked with `IsLibraryContentMixin` (quests, campaigns and badges) have an
    identity that survives the crossing; the rest describe the deck rather than the
    content, and a rank or a course on another deck is not the same rank or course. Those
    are stripped, because there is nothing on the far side for them to point at (#2450).

    Every prerequisite is listed either way, because the name is what lets the destination
    say which requirement it ended up without: one it cannot express (#2450) and one it
    simply does not have (#2399) are the same loss from the teacher's side.

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest whose prerequisites to read.

    Returns:
        list[dict]: one `{'import_id': UUID | None, 'name': str}` per prerequisite. A
        `None` import_id marks one that can never travel, so the destination reports it
        as missing rather than looking for something that was never sent.
    """
    prereqs = []
    for prereq in quest.prereqs():
        target = prereq.get_prereq()
        shareable = IsLibraryContentMixin.is_shareable_model(type(target))
        prereqs.append({
            'import_id': target.import_id if shareable else None,
            'name': str(target),
        })

    return prereqs


def _write_campaign(snapshot):
    """Find or create the destination's copy of a campaign.

    Matched by `import_id` first, then by title. The title fallback is there because
    `Category.title` is unique per deck: without it, importing a campaign whose title the
    destination already uses could not create a second one, it would fail validation and
    reject the whole import. So the choice is to attach to the campaign of that name, or
    to block the import until the teacher renames their own campaign.

    The cost is that two unrelated campaigns sharing a title are treated as one, and the
    imported quests land in the campaign the teacher already had. That is visible and
    recoverable (the quests are there, and can be moved), where a blocked import is
    neither, which is why it is the behaviour chosen here.

    A campaign created here arrives unpublished, like the quests inside it.

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


def _write_prereqs(quest, prereqs):
    """Rebuild the prerequisites whose targets exist on this deck, and report the rest.

    A prerequisite can only point at a row that is actually here, so one whose target the
    deck does not have cannot be rebuilt. Rather than dropping it in silence, the name is
    returned so the caller can tell the teacher what gating did not come with the quest.
    That matters because the loss fails *open*: a quest that arrives with its gate missing
    is more available than its author intended, not less (#2399).

    This only ever adds. It deliberately does not reconcile the destination's prerequisites
    with the source's, because they are not a copy of each other: once a quest is on a
    deck, the teacher gates it into their own map with prerequisites that exist only there
    and appear in no snapshot. Removing whatever is absent from the source would delete
    exactly those, silently. The cost of adding only is that a prerequisite removed
    upstream lingers here, which leaves the quest more gated than intended: that fails
    closed and the teacher can undo it, where deleting their own gating would not.

    Must be called from within the destination schema context.

    Args:
        quest (Quest): the freshly written quest.
        prereqs (list[dict]): `{'import_id', 'name'}` entries from `_snapshot_prereqs`.

    Returns:
        list[str]: the names of the prerequisites this deck does not have.
    """
    from badges.models import Badge

    already_required = {p.get_prereq() for p in quest.prereqs()}
    unmet = []

    for prereq in prereqs:
        if prereq['import_id'] is None:
            # Stripped on the way out because its target cannot cross at all (a rank, a
            # course). Still worth naming: the gate is gone either way (#2450).
            unmet.append(prereq['name'])
            continue

        target = Quest.objects.all_including_archived().filter(import_id=prereq['import_id']).first()
        if target is None:
            target = Category.objects.filter(import_id=prereq['import_id']).first()
        if target is None:
            target = Badge.objects.filter(import_id=prereq['import_id']).first()

        if target is None:
            unmet.append(prereq['name'])
        elif target not in already_required:
            Prereq.add_simple_prereq(quest, target)
            already_required.add(target)

    return unmet


def _write_questions(quest, questions):
    """Make this deck's copy of a quest ask exactly the questions it travelled with.

    Matched by ordinal, which is the only identity a question has across schemas: it
    carries no import_id, and the model already holds one question per ordinal per quest.
    A question at an ordinal the quest already uses is updated in place rather than
    replaced, so answers students gave stay attached to the question they answered.

    Ordinals the arriving quest does not use are deleted, which is what makes re-sharing a
    quest whose author removed a question actually remove it here. Answers to a deleted
    question survive it (`QuestionSubmission.question` is SET_NULL) and show in the marking
    view as answers to a question that is gone.

    Replacing rather than merging is the same bargain the rest of the quest is written
    under: a re-import overwrites the quest's own instructions and title with the shared
    version, so a question the destination added to an imported quest goes the same way as
    an edit it made to that quest's text.

    Must be called from within the destination schema context.

    Args:
        quest (Quest): the freshly written quest.
        questions (list[dict]): copied field values, from `_snapshot_questions`.

    Raises:
        LibraryTransferError: if a question cannot be written.
    """
    superseded = {question.ordinal: question for question in Question.objects.filter(quest=quest)}

    for fields in questions:
        question = superseded.pop(fields['ordinal'], None) or Question(quest=quest)
        for name, value in fields.items():
            setattr(question, name, value)

        try:
            with transaction.atomic():
                question.full_clean()
                question.save()
        except ValidationError as error:
            raise LibraryTransferError(
                f"'{quest.name}' could not be copied: question {fields['ordinal']}: {_describe(error)}"
            ) from error
        except IntegrityError as error:
            raise LibraryTransferError(
                f"'{quest.name}' could not be copied: question {fields['ordinal']}: {error}"
            ) from error

    Question.objects.filter(pk__in=[question.pk for question in superseded.values()]).delete()


def write_quests(writes, *, with_campaign):
    """Write several snapshotted quests into the current schema, then link them up.

    Prerequisites are linked in a second pass, once every quest in the batch exists. A
    prerequisite can only point at a row that is already there, so linking as each quest
    is written would drop any prerequisite pointing at a quest later in the batch, and
    which quests survived would depend on the order they happened to be written in.

    Must be called from within the destination schema context.

    Args:
        writes (list[tuple[dict, bool, dict | None]]): one `(snapshot, published,
            field_overrides)` triple per quest: the snapshot to write, the published
            state to give it, and any field values to replace on the way in (used by the
            conflict-copy path to give a copy its own `import_id` and name).
        with_campaign (bool): whether to attach (and if needed create) each quest's
            campaign.

    Returns:
        TransferResult: the written quests, the names of any prerequisites the destination
        does not have, and the General Info blocks that did not come with them.

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

        # Second pass, so a prerequisite between two quests of this batch is linked
        # whichever order they were written in.
        unmet = []
        for (snapshot, _, _), quest in zip(writes, written):
            unmet.extend(_write_prereqs(quest, snapshot['prereqs']))

    dropped_common_data = sorted({
        snapshot['common_data_title'] for snapshot, _, _ in writes if snapshot['common_data_title']
    })

    return TransferResult(
        quests=written,
        unmet_prereqs=sorted(set(unmet)),
        dropped_common_data=dropped_common_data,
    )


def _write_quest_row(snapshot, *, published, with_campaign, field_overrides=None):
    """Write a quest's own fields, campaign, tags and questions, leaving prerequisites to the caller.

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
    _write_questions(quest, snapshot['questions'])

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
