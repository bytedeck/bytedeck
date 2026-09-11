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

from datetime import date
from typing import NamedTuple

from django.contrib.contenttypes.models import ContentType
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

    `unmet_prereqs` names prerequisites that did not travel, which fails open: the copy
    in the Library ends up with fewer requirements than its author wrote.
    `unmet_alternates` names OR alternatives that did not travel, the opposite loss: the
    prerequisite itself survives, so the copy ends up *stricter* than written, with one
    way to meet it gone (#2549). They are separate lists because the teacher's fix
    differs: a quest that arrives without a prerequisite needs one re-added on the far
    side, a narrowed one needs the alternative shared alongside it.
    `skipped_quests` names quests that were left out of a shared campaign altogether.
    `dropped_common_data` names the shared General Info blocks the copy arrives without.

    `renamed_quests` is the odd one out: nothing was lost, but a name was changed to get
    the copy in, so it is reported to whoever is standing in front of it (#2364).
    `renamed_campaign` is the same thing for the campaign's own title (#2532).
    """

    quests: list
    unmet_prereqs: list
    unmet_alternates: list = ()
    skipped_quests: list = ()
    dropped_common_data: list = ()
    renamed_quests: list = ()
    renamed_campaign: tuple = None


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


def build_available_name(name, taken_names, suffix, max_len):
    """Return a version of `name` that nothing in the destination schema is using.

    `Quest.name` and `Category.title` are both unique per schema, so a copy whose name is
    already spoken for cannot be written at all. This builds the name that gets it in, and
    nothing more: whether a collision should be resolved by renaming at all is the caller's
    decision, not this function's, and the callers do not all answer it the same way.

    Quest names are renamed in both directions: pushing a second copy of a quest already in
    the Library (" (Exported on ...)"), and pulling one onto a deck that wrote its own quest
    of that name (" (Imported on ...)").

    Campaign titles are renamed on the way *in* only. A deck importing a campaign whose
    title it has given to an unrelated campaign gets a renamed copy (#2532), but a push to
    the Library does not: `_write_campaign` is left to fail validation and the sharing view
    refuses, because a title the sharer chose should not be changed on the way out and
    published to every other deck under something they did not pick (#2531, #2534).

    Args:
        name (str): the name the copy would like to keep.
        taken_names (set[str]): every name already spoken for in the destination schema.
            Must include archived quests: they still hold their name against the unique
            constraint even though the default manager hides them.
        suffix (str): what to append to distinguish the copy, e.g. " (Imported on
            2026-08-17)". Numbered when even the suffixed name is taken.
        max_len (int): the destination field's max_length, to truncate to.

    Returns:
        str: a name not in `taken_names`, truncated to fit `max_len`.
    """
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
        (a campaign snapshot or None), `prereqs` (its prerequisite conditions, each a target
        with its NOT/count flags and optional OR half), `questions` (its submission
        questions) and `common_data_title` (the General Info block it uses, which does
        not travel).
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
    so they travel with it (#2162). They ride inside the quest's snapshot rather than
    travelling on their own, and each carries its `import_id`, which is what pairs it with
    the right row on the far side (`_write_questions`).

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest whose questions to read.

    Returns:
        list[dict]: one dict of copied field values per question, ordered by ordinal.
    """
    copied = _copied_field_names(Question, QUESTION_FIELDS_NOT_COPIED)

    return [{name: _read_field(question, name) for name in copied} for question in quest.question_set.all()]


def _snapshot_target(target, invert, count):
    """One side of a prerequisite condition, as a portable id with its own flags.

    Args:
        target: the model instance this side of the condition points at.
        invert (bool): the side's NOT flag.
        count (int): how many times the target must be met.

    Returns:
        dict: `import_id` (UUID, or None for a target that can never travel), `name`,
        `invert` and `count`.
    """
    shareable = IsLibraryContentMixin.is_shareable_model(type(target))
    return {
        'import_id': target.import_id if shareable else None,
        'name': str(target),
        'invert': invert,
        'count': count,
    }


def _snapshot_prereqs(quest):
    """The shareable prerequisites of a quest, as portable conditions with readable names.

    A prerequisite is a generic foreign key, so it can point at any prerequisite model.
    Only those marked with `IsLibraryContentMixin` (quests, campaigns and badges) have an
    identity that survives the crossing; the rest describe the deck rather than the
    content, and a rank or a course on another deck is not the same rank or course. Those
    are stripped, because there is nothing on the far side for them to point at (#2450).

    Every prerequisite is listed either way, because the name is what lets the destination
    say which requirement it ended up without: one it cannot express (#2450) and one it
    simply does not have (#2399) are the same loss from the teacher's side.

    The whole condition travels, not just the target: the NOT flag, the required count,
    and the alternate OR half (with its own flags) are part of what the author wrote, and
    a prerequisite stripped of its NOT would mean the opposite of what it said (#2535).

    Must be called from within the source schema context.

    Args:
        quest (Quest): the quest whose prerequisites to read.

    Returns:
        list[dict]: one entry per prerequisite: `import_id` (UUID | None), `name`,
        `invert`, `count`, and `alternate` (None, or those same four keys for the OR
        half). A `None` import_id marks a target that can never travel, so the
        destination reports it as missing rather than looking for something that was
        never sent.
    """
    prereqs = []
    for prereq in quest.prereqs():
        entry = _snapshot_target(prereq.get_prereq(), prereq.prereq_invert, prereq.prereq_count)
        or_target = prereq.get_or_prereq()
        entry['alternate'] = (
            _snapshot_target(or_target, prereq.or_prereq_invert, prereq.or_prereq_count)
            if or_target is not None else None
        )
        prereqs.append(entry)

    return prereqs


def _write_campaign(snapshot, *, rename_on_clash=False):
    """Find or create the destination's copy of a campaign.

    Matched by `import_id`, the only identity a campaign keeps across schemas. A campaign
    the destination already holds under that id is returned as it is.

    `Category.title` is unique per schema, so a campaign whose title the destination has
    given to some *other* campaign cannot be written under it. `rename_on_clash` decides
    what happens then, because the two directions want opposite answers (#2532):

    * Importing onto a deck renames the arriving copy, exactly as a clashing quest name is
      renamed, so the teacher's own campaign is left alone and both survive.
    * Pushing to the Library does not, so the write raises and the sharing view refuses
      with a message. A name the sharer chose should not be changed on the way out and
      published to every other deck under something they did not pick (#2531, #2534).

    A campaign created here arrives unpublished, like the quests inside it.

    Must be called from within the destination schema context.

    Args:
        snapshot (dict): a campaign snapshot from `snapshot_campaign`.
        rename_on_clash (bool): give the arriving copy a free title when the destination
            has a different campaign under this one.

    Returns:
        tuple[Category, tuple[str, str] | None]: the destination's campaign, and the
        `(wanted, given)` titles when it had to be renamed to get in.
    """
    existing = Category.objects.filter(import_id=snapshot['import_id']).first()
    if existing is not None:
        return existing, None

    wanted = snapshot['title']
    taken_titles = set(Category.objects.values_list('title', flat=True))
    renamed = None

    if wanted in taken_titles:
        if not rename_on_clash:
            # Left to fail validation, which the sharing view turns into a refusal naming
            # the clash. Renaming here would publish the campaign under a title its author
            # did not choose.
            given = wanted
        else:
            given = build_available_name(
                wanted, taken_titles, f" (Imported on {date.today()})",
                Category._meta.get_field('title').max_length or 50,
            )
            renamed = (wanted, given)
    else:
        given = wanted

    campaign = Category(published=False, **{**snapshot, 'title': given})
    campaign.full_clean()
    campaign.save()

    return campaign, renamed


def _write_prereqs(quest, prereqs, *, refresh_matched=False):
    """Rebuild the prerequisites whose targets exist on this deck, and report the rest.

    A prerequisite can only point at a row that is actually here, so one whose target the
    deck does not have cannot be rebuilt. Rather than dropping it in silence, the name is
    returned so the caller can tell the teacher which prerequisite did not come with the
    quest. That matters because the loss fails *open*: a quest that arrives with a
    prerequisite missing is more available than its author intended, not less (#2399).

    This never deletes. It deliberately does not reconcile the destination's prerequisites
    with the source's, because they are not a copy of each other: once a quest is on a
    deck, the teacher works it into their own map with prerequisites that exist only
    there and appear in no snapshot. Removing whatever is absent from the source would
    delete exactly those, silently. The cost is that a prerequisite removed upstream
    lingers here, which leaves the quest with more requirements than intended: that fails
    closed and the teacher can undo it, where deleting their own prerequisites would
    not.

    The whole condition is rebuilt, not just the link: the NOT flag, the required count,
    and the alternate OR half travel with the row (#2535). The OR half needs a target of
    its own here, under the same rule as the main one. When that target is missing, the
    row is written without its alternate, which fails *closed* (the prerequisite is
    stricter than written, not looser), and the alternate is named in its own list so the
    caller can describe that loss for what it is rather than as a dropped prerequisite
    (#2549). When the
    main target is missing, the whole condition is unbuildable and only the main target
    is named: the row it identifies never arrives, alternate and all.

    `refresh_matched` decides what happens to a prerequisite the destination already has
    on the same target. The push into the Library refreshes it, so re-sharing updates the
    condition's flags the way it already updates the quest's own fields. An import into a
    deck leaves it alone: that copy is the teacher's to adjust, and their adjustments
    must survive a campaign re-import.

    Must be called from within the destination schema context.

    Args:
        quest (Quest): the freshly written quest.
        prereqs (list[dict]): condition entries from `_snapshot_prereqs`.
        refresh_matched (bool): update the condition of an existing prerequisite on the
            same target, rather than leaving it as the destination has it.

    Returns:
        tuple[list[str], list[str]]: the names of the prerequisite targets this deck
        does not have (the prerequisite is dropped, failing open), and the names of the
        OR alternatives it does not have (the prerequisite survives without them,
        failing closed).
    """
    existing_by_target = {p.get_prereq(): p for p in quest.prereqs()}
    unmet = []
    unmet_alternates = []

    for prereq in prereqs:
        if prereq['import_id'] is None:
            # Stripped on the way out because its target cannot cross at all (a rank, a
            # course). Still worth naming: the prerequisite is gone either way (#2450).
            unmet.append(prereq['name'])
            continue

        target = _find_prereq_target(prereq['import_id'])
        if target is None:
            unmet.append(prereq['name'])
            continue

        row = existing_by_target.get(target)
        if row is not None and not refresh_matched:
            # the destination's own copy of this prerequisite stays as the teacher has it
            continue

        alternate = prereq['alternate']
        or_target = None
        if alternate is not None:
            if alternate['import_id'] is not None:
                or_target = _find_prereq_target(alternate['import_id'])
            if or_target is None:
                unmet_alternates.append(alternate['name'])

        if row is None:
            row = Prereq(
                parent_content_type=ContentType.objects.get_for_model(quest),
                parent_object_id=quest.id,
                prereq_content_type=ContentType.objects.get_for_model(target),
                prereq_object_id=target.id,
            )
        row.prereq_invert = prereq['invert']
        row.prereq_count = prereq['count']
        if or_target is not None:
            row.or_prereq_content_type = ContentType.objects.get_for_model(or_target)
            row.or_prereq_object_id = or_target.id
            row.or_prereq_invert = alternate['invert']
            row.or_prereq_count = alternate['count']
        else:
            # the condition has no (buildable) alternate, so a refreshed row sheds any
            # stale one and a new row gets the fields' defaults
            row.or_prereq_content_type = None
            row.or_prereq_object_id = None
            row.or_prereq_invert = False
            row.or_prereq_count = 1
        row.full_clean()
        row.save()
        existing_by_target[target] = row

    return unmet, unmet_alternates


def _find_prereq_target(import_id):
    """The destination's row for a prerequisite target, whichever shareable model it is.

    Args:
        import_id (UUID): the target's cross-schema identity.

    Returns:
        Quest | Category | Badge | None: the local row, or None when this deck does not
        have it.
    """
    from badges.models import Badge

    target = Quest.objects.all_including_archived().filter(import_id=import_id).first()
    if target is None:
        target = Category.objects.filter(import_id=import_id).first()
    if target is None:
        target = Badge.objects.filter(import_id=import_id).first()
    return target


def _write_questions(quest, questions):
    """Make this deck's copy of a quest ask exactly the questions it travelled with.

    Matched by `import_id`, the identity a question keeps across schemas and across a
    reorder. A question the destination already has is updated in place rather than
    replaced, so answers students gave stay attached to the question they answered.

    Ordinal cannot serve as that identity, because reordering is implemented as swapping
    ordinals (`QuestionMoveView._swap_ordinals`): after the author reorders a shared quest,
    the row sitting at a given ordinal here is a different question than the one arriving
    with it, and updating it in place would leave every answer already published against it
    displayed under another question's text (#2566). Ordinal now only decides the order
    students answer in.

    Questions the arriving quest no longer asks are deleted, which is what makes re-sharing
    a quest whose author removed a question actually remove it here. Answers to a deleted
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
    existing = {question.import_id: question for question in Question.objects.filter(quest=quest)}
    arriving = {fields['import_id'] for fields in questions}

    Question.objects.filter(
        pk__in=[question.pk for import_id, question in existing.items() if import_id not in arriving]
    ).delete()

    # Every ordinal is about to be reassigned, and (quest, ordinal) is unique, so a question
    # that keeps its row but changes place would collide with whichever row is still standing
    # there. Parking the rows being kept above every ordinal in play empties the range first.
    # A plain UPDATE, not a validated save: this is bookkeeping between two writes of the same
    # field, and the value is deliberately outside the range the quest ends up using.
    kept = [question for import_id, question in existing.items() if import_id in arriving]
    if kept:
        parking = max(
            [question.ordinal for question in existing.values()]
            + [fields['ordinal'] for fields in questions]
        ) + 1
        for offset, question in enumerate(kept):
            Question.objects.filter(pk=question.pk).update(ordinal=parking + offset)

    for fields in questions:
        question = existing.get(fields['import_id']) or Question(quest=quest)
        for name, value in fields.items():
            setattr(question, name, value)

        try:
            with transaction.atomic():
                question.full_clean()
                question.save()
        except ValidationError as error:
            raise LibraryTransferError(
                f"'{quest.name}' could not be copied: question {fields['ordinal']}: {describe_validation_error(error)}"
            ) from error
        except IntegrityError as error:
            raise LibraryTransferError(
                f"'{quest.name}' could not be copied: question {fields['ordinal']}: {error}"
            ) from error


def write_quests(writes, *, with_campaign, refresh_matched_prereqs=False, rename_campaign_on_clash=False):
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
        refresh_matched_prereqs (bool): update the condition of prerequisites the
            destination already has on the same target (the Library push does; a deck
            import does not, see `_write_prereqs`).
        rename_campaign_on_clash (bool): give an arriving campaign a free title when the
            destination has a different campaign under that one (a deck import does; the
            Library push does not, see `_write_campaign`).

    Returns:
        TransferResult: the written quests, the names of any prerequisite targets and
        OR alternatives the destination does not have, and the General Info blocks that
        did not come with them.

    Raises:
        LibraryTransferError: if any quest cannot be written.
    """
    # All of the batch or none of it: a half-written campaign would leave the deck holding
    # some quests of a set whose prerequisites reference the ones that never arrived.
    with transaction.atomic():
        written = []
        renamed_campaign = None
        for snapshot, published, overrides in writes:
            quest, campaign_rename = _write_quest_row(
                snapshot, published=published, with_campaign=with_campaign, field_overrides=overrides,
                rename_campaign_on_clash=rename_campaign_on_clash,
            )
            written.append(quest)
            # Every quest of a batch carries the same campaign, so the first rename is the
            # rename: recording each would report the same one once per quest.
            renamed_campaign = renamed_campaign or campaign_rename

        # Second pass, so a prerequisite between two quests of this batch is linked
        # whichever order they were written in.
        unmet = []
        unmet_alternates = []
        for (snapshot, _, _), quest in zip(writes, written):
            quest_unmet, quest_alternates = _write_prereqs(
                quest, snapshot['prereqs'], refresh_matched=refresh_matched_prereqs)
            unmet.extend(quest_unmet)
            unmet_alternates.extend(quest_alternates)

    dropped_common_data = sorted({
        snapshot['common_data_title'] for snapshot, _, _ in writes if snapshot['common_data_title']
    })

    return TransferResult(
        quests=written,
        unmet_prereqs=sorted(set(unmet)),
        unmet_alternates=sorted(set(unmet_alternates)),
        dropped_common_data=dropped_common_data,
        renamed_campaign=renamed_campaign,
    )


def _write_quest_row(snapshot, *, published, with_campaign, field_overrides=None, rename_campaign_on_clash=False):
    """Write a quest's own fields, campaign, tags and questions, leaving prerequisites to the caller.

    An existing row with the same `import_id` is updated rather than duplicated, which is
    what makes re-sharing a quest refresh the Library's copy instead of adding a second.

    Must be called from within the destination schema context.

    Args:
        snapshot (dict): a quest snapshot from `snapshot_quest`.
        published (bool): the published state to give the written quest.
        with_campaign (bool): whether to attach (and if needed create) the campaign.
        field_overrides (dict | None): field values to replace on the way in.
        rename_campaign_on_clash (bool): passed to `_write_campaign`.

    Returns:
        tuple[Quest, tuple[str, str] | None]: the written quest, without its prerequisites
        yet, and the `(wanted, given)` titles when its campaign had to be renamed.

    Raises:
        LibraryTransferError: if the quest cannot be written.
    """
    fields = dict(snapshot['fields'], **(field_overrides or {}))
    import_id = fields['import_id']

    quest = Quest.objects.all_including_archived().filter(import_id=import_id).first() or Quest(import_id=import_id)
    for name, value in fields.items():
        setattr(quest, name, value)
    quest.published = published

    renamed_campaign = None
    if with_campaign and snapshot['campaign'] is not None:
        quest.campaign, renamed_campaign = _write_campaign(
            snapshot['campaign'], rename_on_clash=rename_campaign_on_clash)

    try:
        with transaction.atomic():
            quest.full_clean(exclude=['campaign'])
            quest.save()
    except ValidationError as error:
        raise LibraryTransferError(f"'{fields['name']}' could not be copied: {describe_validation_error(error)}") from error
    except IntegrityError as error:
        raise LibraryTransferError(f"'{fields['name']}' could not be copied: {error}") from error

    quest.tags.set(snapshot['tags'])
    _write_questions(quest, snapshot['questions'])

    return quest, renamed_campaign


def describe_validation_error(error):
    """Render a ValidationError as one readable sentence.

    Args:
        error (ValidationError): the error raised by `full_clean`.

    Returns:
        str: the messages, joined, without Django's dict-and-list punctuation.
    """
    if hasattr(error, 'message_dict'):
        return '; '.join(f"{field}: {' '.join(messages)}" for field, messages in error.message_dict.items())

    return ' '.join(error.messages)
