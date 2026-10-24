import html

from django.db.models import Case, Max, Value, When
from django.template.loader import render_to_string

from .models import QuestionSubmission, QuestionType


def save_draft_file_answers(question_formset, uploaded_files):
    """Persist a bound formset's file answers onto their draft rows, and return how many
    were saved.

    A browser never repopulates a file input, so any response that rebuilds the page comes
    back with every file field empty. Without this the student's upload is gone with nothing
    to say so: a required file question demands a file they did attach, and an optional one
    publishes empty (#2165). Keeping the upload on the draft row means it survives the round
    trip, exactly as autosaved text answers do; the Save Draft flow stores files through the
    same helper (#1459), so a draft-saved answer and a kept one are the same thing.

    Only rows whose own file validated are saved: a file rejected for type or size never
    reaches ``cleaned_data``, so its error stands and nothing is stored. Rows the student did
    not upload to this time are skipped, so an earlier file is never overwritten by a
    re-submit that left the field alone.

    Each write touches the file column and nothing else, so a save that lands after the
    student's submit has published these answers adds the file they chose to the published
    answer rather than reverting the row to a draft (#2565).

    Args:
        question_formset: the bound answer formset, with validation already run.
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
        # This reads the snapshot the formset was built from, so it catches a row that was
        # already published when this request started, not one published since: the formset
        # is only ever built over this submission's own unpublished draft rows, so that
        # cannot happen unless a caller widens the queryset. A row published in the meantime
        # is what `update_fields` on the save below is for.
        if not row.pk or row.comment_id is not None:  # pragma: no cover
            continue

        row.response_file = upload
        row.full_clean()
        # Only the file, never the whole row. This instance was loaded before the request
        # that is now publishing these answers ran, so its `comment` is a snapshot: a full
        # save would write that stale NULL back over a `comment_id` the student's submit
        # has just set, quietly unpublishing an answer they did submit (#2565).
        row.save(update_fields=["response_file", "datetime_last_edit"])
        saved += 1
    return saved


def discard_draft_question_submissions(quest_submission):
    """Delete a submission's unpublished draft answer rows, and return how many were deleted.

    Called when a submission is skipped (approved as a transfer): the student never submitted
    this work and the quest is being waived, so nothing will ever publish those rows. Only
    answers attached to a comment are rendered anywhere, so left alone the drafts would be
    invisible and permanent (#2164).

    Published rows are untouched, so a submission that was completed once, or returned and
    re-drafted, keeps the answers it already published with their comments.

    Args:
        quest_submission: the QuestSubmission being skipped.

    Returns:
        int: how many draft rows were deleted.
    """
    deleted, _ = QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True
    ).delete()
    return deleted


def sync_draft_question_submissions(quest_submission):
    """Ensure exactly one draft answer row exists per question the student answers in this
    hand-in, and return the queryset of draft rows to build the answer formset from.

    Those are all the quest's questions the first time, and after a return only the ones
    marked wrong (`questions_to_answer`, #2933). Called every time the answer formset is built
    (submission page render and complete POST), so the formset always matches the quest's
    *current* question set:

    * A question added after the student started gets a fresh draft row here.
    * A deleted question's rows have question=None (SET_NULL). A *published* one is kept:
      it renders with its comment as part of the student's record, and is excluded from the
      returned queryset so it can't block or crash the formset. An unpublished one is
      deleted, because nothing can ever reach it again: answers display only through
      ``comment.question_submissions``, which a NULL comment excludes, and the publish step
      filters on ``question__isnull=False``. Left alone it would sit in the schema forever,
      along with an uploaded file of up to 16 MiB (#2567).
    * Published rows (comment set) belong to an earlier submission cycle and are ignored,
      so a returned-and-resubmitted quest starts fresh drafts, a text one starting with the
      answer it replaces.
    * Duplicate draft rows for the same question are healed by keeping one and deleting the
      rest (preferring a row with content, then the most recently edited). Duplicates can
      arise from two concurrent first renders racing this function, or from a published
      comment being deleted (its answers revert to draft via SET_NULL) while a new cycle's
      draft for the same question already exists. A DB uniqueness constraint can't be used
      here precisely because of that revert path: it would turn the comment deletion into
      an IntegrityError.
    """
    # Unpublished answers to a question that has since been deleted: invisible to every
    # code path and reachable by none, so this is their only chance to be cleaned up
    # (#2567). Published ones are untouched: those still render with their comment.
    #
    # The uploaded file goes first, and has to. Django has not deleted a FileField's
    # storage on row delete since 1.3, so dropping the row alone would leave the file on
    # disk with nothing left in the database pointing at it: worse than the orphan being
    # fixed, because the row at least named the file a sweep could find. Deleted one row at
    # a time rather than through the queryset, since QuerySet.delete() never opens the
    # files. save=False because the row is about to be deleted anyway.
    orphans = QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True, question__isnull=True
    )
    for orphan in orphans:
        if orphan.response_file:
            orphan.response_file.delete(save=False)
    orphans.delete()

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

    latest_answers = latest_published_answers(quest_submission)
    QuestionSubmission.objects.bulk_create([
        QuestionSubmission(
            quest_submission=quest_submission, question=question,
            # A text answer coming back to be fixed starts with what the student wrote, so they
            # correct it rather than type it out again (#2933). A file answer starts empty: a
            # file input can't be filled in, and the earlier file shows with its comment above.
            response_text=_previous_text(latest_answers.get(question.id)),
        )
        for question in questions_to_answer(quest_submission, latest_answers)
        if question.id not in keeper_by_question
    ])
    return QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True, question__isnull=False
    )


def render_answer_file(answer):
    """Render the file saved with a draft answer to a file question, with its Delete button.

    The submission page shows this in the answer's control, and the draft-save and delete
    endpoints hand it back so the page can replace it without a reload (#2925). Rendering it in
    one place keeps what the student sees after a save or a removal identical to what a fresh
    page would show.

    Args:
        answer (QuestionSubmission): the draft answer.

    Returns:
        str: the rendered HTML, empty when the answer holds no file.
    """
    return render_to_string("questions/snippets/answer_file_saved.html", {"answer": answer})


def latest_published_answers(quest_submission):
    """Return each question's most recently published answer on a submission.

    Every hand-in publishes its answers with its own comment, and comments are numbered as they
    are made, so the answer with the highest comment id is the one handed in last.

    Args:
        quest_submission: the QuestSubmission whose answers to read.

    Returns:
        dict: question id to the QuestionSubmission published for it last.
    """
    latest = {}
    for answer in QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=False, question__isnull=False,
    ).select_related("question").order_by("comment_id"):
        latest[answer.question_id] = answer
    return latest


def questions_to_answer(quest_submission, latest_answers=None):
    """Return the quest's questions the student answers in the submission's current hand-in.

    All of them the first time. After a return, only those the teacher marked wrong when it
    came back (#2933), so a quest returned with nothing marked wrong brings back just the
    comment box. A question with no marked answer comes back too: one added to the quest since
    the student last handed it in, or one answered before answers were marked at all, which is
    how a return worked before marking existed.

    Args:
        quest_submission: the QuestSubmission being worked on.
        latest_answers (dict): `latest_published_answers(quest_submission)`, if the caller
            has it already.

    Returns:
        list: the Question objects to answer, in the quest's order.
    """
    if latest_answers is None:
        latest_answers = latest_published_answers(quest_submission)
    return [
        question for question in quest_submission.quest.question_set.all()
        if question.id not in latest_answers or latest_answers[question.id].is_correct is not True
    ]


def _previous_text(answer):
    """The text of an answer coming back to be fixed, or nothing for a file answer or a new
    question.

    A short answer is stored HTML-escaped (`QuestionSubmissionForm.clean_response_text`), so a
    student's ``R&D`` is kept as ``R&amp;D``. Its text input shows a value as plain text, so the
    draft starts with the text as the student typed it: escaped, the field would show the entity
    itself and could run past the field's 200-character limit. A long answer's editor shows HTML,
    so its stored value is the right start as it is.

    Args:
        answer (QuestionSubmission): the question's latest published answer, or None.

    Returns:
        str: the text to start the new draft with.
    """
    if answer is None or answer.question.type == QuestionType.FILE_UPLOAD:
        return ""
    if answer.question.type == QuestionType.SHORT_ANSWER:
        return html.unescape(answer.response_text)
    return answer.response_text


def finalize_answer_marks(quest_submission):
    """Set each answer of the submission's latest hand-in right or wrong, as the teacher marked it.

    Called when a teacher returns or approves the quest (#2933). Until then the X a teacher
    toggles beside an answer is seen only by staff (`marked_wrong`); from here every answer of
    that hand-in shows a check or an X (`is_correct`), and on a return only the wrong ones come
    back for the student to answer again (`questions_to_answer`). Answers already marked are
    left as they are, so an earlier hand-in keeps the marks it came back with.

    Only a submission handed in and awaiting review is marked. One returned and not yet handed
    in again has no hand-in under review: its latest one was judged when it came back, so
    approving it from there leaves those answers as they are. Nor is an approved one: approving
    it already marked its answers, unless it was approved before answers were marked at all, and
    then a return brings every question back, as a return did before marking existed.

    Args:
        quest_submission: the QuestSubmission being returned or approved.

    Returns:
        int: how many answers were marked.
    """
    if not quest_submission.is_completed or quest_submission.is_approved:
        return 0
    latest_comment_id = QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=False,
    ).aggregate(Max("comment_id"))["comment_id__max"]
    if latest_comment_id is None:
        return 0
    # One statement, so an X saved while this runs lands either before it, and counts, or after
    # it, and is refused (ajax_mark_answer writes only while an answer is unmarked).
    return QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment_id=latest_comment_id, is_correct__isnull=True,
    ).update(is_correct=Case(When(marked_wrong=True, then=Value(False)), default=Value(True)))
