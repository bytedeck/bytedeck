from siteconfig.models import SiteConfig

from .models import QuestionSubmission


def questions_enabled_for(quest):
    """Whether submission questions are active for this quest: the deck has opted in via
    SiteConfig.enable_submission_questions AND the quest has at least one question."""
    return SiteConfig.get().enable_submission_questions and quest.question_set.exists()


def sync_draft_question_submissions(quest_submission):
    """Ensure one draft answer row exists per current question of the submission's quest,
    and return the queryset of draft rows to build the answer formset from.

    Called every time the answer formset is built (submission page render and complete POST),
    so the formset always matches the quest's *current* question set:

    * A question added after the student started gets a fresh draft row here.
    * A deleted question's rows have question=None (SET_NULL) and are excluded from the
      returned queryset, so they can't block or crash the formset; the rows themselves are
      kept (any content may still interest a marker).
    * Published rows (comment set) belong to an earlier submission cycle and are ignored,
      so a returned-and-resubmitted quest starts a fresh set of drafts.
    """
    questions = quest_submission.quest.question_set.all()
    existing_question_ids = set(
        QuestionSubmission.objects.filter(
            quest_submission=quest_submission, comment__isnull=True
        ).values_list("question_id", flat=True)
    )
    QuestionSubmission.objects.bulk_create([
        QuestionSubmission(quest_submission=quest_submission, question=question)
        for question in questions
        if question.id not in existing_question_ids
    ])
    return QuestionSubmission.objects.filter(
        quest_submission=quest_submission, comment__isnull=True, question__isnull=False
    )
