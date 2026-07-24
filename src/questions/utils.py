from .models import QuestionSubmission


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
