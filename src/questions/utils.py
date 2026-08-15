from .models import QuestionSubmission


def save_draft_file_answers(question_formset, uploaded_files):
    """Persist the file answers of an invalid formset onto their draft rows, and return how
    many were saved.

    A browser never repopulates a file input, so when the answer formset fails validation the
    re-rendered page comes back with every file field empty. Without this the student's upload
    is gone with nothing to say so: a required file question demands a file they did attach,
    and an optional one publishes empty (#2165). Keeping the upload on the draft row means it
    survives the round trip, exactly as autosaved text answers already do.

    Only rows whose own file validated are saved: a file rejected for type or size never
    reaches ``cleaned_data``, so its error stands and nothing is stored. Rows the student did
    not upload to this time are skipped, so an earlier file is never overwritten by a
    re-submit that left the field alone.

    Args:
        question_formset: the bound, invalid answer formset.
        uploaded_files: the request's ``FILES``, used to tell a fresh upload from an untouched
            field (the field is absent from ``FILES`` when nothing new was chosen).

    Returns:
        int: how many draft rows had a file saved.
    """
    saved = 0
    for form in question_formset.forms:
        if form.add_prefix("response_file") not in uploaded_files:
            continue
        # cleaned_data is missing entirely if the form never ran validation, and omits
        # response_file when the upload itself was rejected for type or size
        upload = getattr(form, "cleaned_data", {}).get("response_file")
        if not upload:
            continue

        row = form.instance
        # Defensive: the formset is only ever built over this submission's own unpublished
        # draft rows, so a saved-but-published row cannot reach here. Guarded anyway so that
        # widening the caller's queryset can never overwrite a finished cycle's answer.
        if not row.pk or row.comment_id is not None:  # pragma: no cover
            continue

        row.response_file = upload
        row.full_clean()
        row.save()
        saved += 1
    return saved


def sync_draft_question_submissions(quest_submission):
    """Ensure exactly one draft answer row exists per current question of the submission's
    quest, and return the queryset of draft rows to build the answer formset from.

    Called every time the answer formset is built (submission page render and complete POST),
    so the formset always matches the quest's *current* question set:

    * A question added after the student started gets a fresh draft row here.
    * A deleted question's rows have question=None (SET_NULL) and are excluded from the
      returned queryset, so they can't block or crash the formset; the rows themselves are
      kept (any content may still interest a marker).
    * Published rows (comment set) belong to an earlier submission cycle and are ignored,
      so a returned-and-resubmitted quest starts a fresh set of drafts.
    * Duplicate draft rows for the same question are healed by keeping one and deleting the
      rest (preferring a row with content, then the most recently edited). Duplicates can
      arise from two concurrent first renders racing this function, or from a published
      comment being deleted (its answers revert to draft via SET_NULL) while a new cycle's
      draft for the same question already exists. A DB uniqueness constraint can't be used
      here precisely because of that revert path — it would turn the comment deletion into
      an IntegrityError.
    """
    drafts = QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True, question__isnull=False
    )

    keeper_by_question = {}
    duplicate_ids = []
    # newest edits first, so the first contentful row seen is the freshest one
    for row in drafts.order_by("-datetime_last_edit"):
        keeper = keeper_by_question.get(row.question_id)
        if keeper is None:
            keeper_by_question[row.question_id] = row
        elif (row.response_text or row.response_file) and not (keeper.response_text or keeper.response_file):
            # this older row has content while the current keeper is empty: keep it instead
            duplicate_ids.append(keeper.id)
            keeper_by_question[row.question_id] = row
        else:
            duplicate_ids.append(row.id)
    if duplicate_ids:
        QuestionSubmission.objects.filter(id__in=duplicate_ids).delete()

    QuestionSubmission.objects.bulk_create([
        QuestionSubmission(quest_submission=quest_submission, question=question)
        for question in quest_submission.quest.question_set.all()
        if question.id not in keeper_by_question
    ])
    return QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True, question__isnull=False
    )
