"""Recording competency evidence for a quest submission.

A submission of a quest with competencies attached holds one CompetencyAssessment per competency:
its latest level in it. Approving the submission records a level for each of the quest's
competencies: the level the teacher chose on the approval form, which starts on the level the
submission already has (a submission returned and approved again) or else the link's default, as
quick approvals and quests that need no teacher approval record too. Commenting on an approved
submission records the levels the teacher changed on the form.

A level recorded for a submission replaces the one it had for that competency, so each quest
counts only its latest rating; the comment that recorded each rating keeps the record of what was
given, and when.

A quest can also ask its students for a self-assessment (Quest.competency_self_assessment): on
handing it in, the student may choose a level in each of its competencies, recorded as an assessment
by the student themself. A submission holds at most one self-assessment per competency, its latest,
kept apart from the teacher's level, which it never replaces or counts toward.
"""

from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.template.defaultfilters import truncatechars
from django.utils.html import format_html, format_html_join

from siteconfig.models import SiteConfig

from .forms import competency_level_field_name, self_assessment_field_name
from .models import CompetencyAssessment, ProficiencyLevel


def approval_links(quest):
    """ The quest's competency links that an approval records evidence for.

    Links to deactivated competencies are left out: a deactivated competency is hidden from
    new use, and new evidence is new use.

    Args:
        quest (Quest): the quest being approved.

    Returns:
        list[QuestCompetency]: the links, in the default (course, category, name) ordering.
    """
    return [link for link in quest.quest_competencies.all() if link.competency.active]


def _levels_by_submission(submissions, self_assessed=False):
    """ The current levels of each of the submissions, in one query: the teacher's, or the student's
    self-assessment.

    Args:
        submissions (list[QuestSubmission]): the submissions, at least one.
        self_assessed (bool): the student's self-assessments rather than the teacher's levels.

    Returns:
        dict[int, dict[int, int]]: submission pk to its current level by competency pk.
    """
    levels = defaultdict(dict)
    assessments = CompetencyAssessment.objects.filter(
        source_content_type=ContentType.objects.get_for_model(submissions[0]),
        source_object_id__in=[submission.pk for submission in submissions],
    )
    assessments = assessments.self_assessments() if self_assessed else assessments.teacher_evidence()
    rows = assessments.order_by('timestamp', 'pk').values_list('source_object_id', 'competency_id', 'level')
    # oldest first, so a later level for a competency replaces an earlier one
    for submission_id, competency_id, level in rows:
        levels[submission_id][competency_id] = level
    return levels


def prefetch_submission_levels(submissions):
    """ Fetch the current levels of many submissions at once, and their students' self-assessments,
    for a page that shows the level controls for each (see submission_levels and
    submission_self_levels).

    Args:
        submissions (iterable of QuestSubmission): the submissions.
    """
    submissions = list(submissions)
    if not submissions:
        return
    levels = _levels_by_submission(submissions)
    self_levels = _levels_by_submission(submissions, self_assessed=True)
    for submission in submissions:
        submission.competency_levels = levels.get(submission.pk, {})
        submission.competency_self_levels = self_levels.get(submission.pk, {})


def submission_levels(submission):
    """ The submission's current level in each competency it has evidence for (its latest
    assessment of each), from prefetch_submission_levels when the page fetched them.

    Args:
        submission (QuestSubmission): the submission.

    Returns:
        dict[int, int]: competency pk to level.
    """
    prefetched = getattr(submission, 'competency_levels', None)
    if prefetched is not None:
        return prefetched
    return _levels_by_submission([submission]).get(submission.pk, {})


def submission_self_levels(submission):
    """ The student's self-assessment of the submission in each competency they self-assessed (their
    latest of each), from prefetch_submission_levels when the page fetched them.

    Args:
        submission (QuestSubmission): the submission.

    Returns:
        dict[int, int]: competency pk to level.
    """
    prefetched = getattr(submission, 'competency_self_levels', None)
    if prefetched is not None:
        return prefetched
    return _levels_by_submission([submission], self_assessed=True).get(submission.pk, {})


def starting_level(link, current):
    """ The level the approval form starts a link's competency on: the submission's current level
    in it, or the link's default when it has none.

    Args:
        link (QuestCompetency): the quest's link to the competency.
        current (dict[int, int]): the submission's current levels (submission_levels).

    Returns:
        int: a ProficiencyLevel value.
    """
    return current.get(link.competency_id, link.default_level)


def posted_level(data, link, start):
    """ The level posted for a link's competency on the approval form, or the level it started on.

    Args:
        data (QueryDict or None): the approval form's POST data, or None when no form was posted.
        link (QuestCompetency): the quest's link to the competency.
        start (int): the level the form started on (starting_level).

    Returns:
        int: a ProficiencyLevel value. Anything posted that isn't one (a hand-made request) falls
        back to the starting level, as a missing value does.
    """
    raw = (data or {}).get(competency_level_field_name(link.competency_id))
    try:
        level = int(raw)
    except (TypeError, ValueError):
        return start
    return level if level in ProficiencyLevel.values else start


def competencies_enabled():
    """ Whether this deck has competencies enabled (the public schema, with no SiteConfig, hasn't).

    Returns:
        bool: True when the deck has a SiteConfig with enable_competencies set.
    """
    config = SiteConfig.get()
    return config is not None and config.enable_competencies


def record_level(submission, link, level, assessed_by):
    """ Record the submission's level in a link's competency, replacing the one it had.

    Args:
        submission (QuestSubmission): the submission; its student is the one assessed.
        link (QuestCompetency): the quest's link to the competency.
        level (int): the ProficiencyLevel value.
        assessed_by (User or None): the teacher, or None when no teacher assessed it.

    Returns:
        CompetencyAssessment: the assessment created.
    """
    source_content_type = ContentType.objects.get_for_model(submission)
    CompetencyAssessment.objects.teacher_evidence().filter(
        source_content_type=source_content_type, source_object_id=submission.pk, competency=link.competency,
    ).delete()
    assessment = CompetencyAssessment(
        user=submission.user,
        competency=link.competency,
        level=level,
        source_content_type=source_content_type,
        source_object_id=submission.pk,
        assessed_by=assessed_by,
    )
    assessment.full_clean()
    assessment.save()
    return assessment


def record_approval_assessments(submission, assessed_by=None, data=None):
    """ Record the competency evidence an approval of the submission gives, if the deck has
    competencies enabled: a level for each of the quest's competencies, the one posted or else the
    one the form started on.

    Args:
        submission (QuestSubmission): the submission just approved; its student is the one assessed.
        assessed_by (User or None): the teacher who approved it, or None for a quest that is
            approved automatically (system-assessed).
        data (QueryDict or None): the approval form's POST data, for the levels the teacher chose.

    Returns:
        list[CompetencyAssessment]: the assessments created, one per competency (empty when the
        flag is off or the quest has no active competencies).
    """
    if not competencies_enabled():
        return []
    current = submission_levels(submission)
    return [
        record_level(submission, link, posted_level(data, link, starting_level(link, current)), assessed_by)
        for link in approval_links(submission.quest)
    ]


def level_changes(submission, data):
    """ The levels a teacher changed on the approval form: each competency whose posted level
    differs from the one the form started on.

    Args:
        submission (QuestSubmission): the submission the form acts on.
        data (QueryDict): the form's POST data.

    Returns:
        list[tuple[QuestCompetency, int]]: each changed link with its new level (empty when the
        flag is off or nothing changed).
    """
    if not competencies_enabled():
        return []
    current = submission_levels(submission)
    changes = []
    for link in approval_links(submission.quest):
        start = starting_level(link, current)
        level = posted_level(data, link, start)
        if level != start:
            changes.append((link, level))
    return changes


def record_level_changes(submission, assessed_by, data):
    """ Record the levels a teacher changed when commenting on an approved submission.

    Args:
        submission (QuestSubmission): the approved submission commented on.
        assessed_by (User): the teacher.
        data (QueryDict): the form's POST data.

    Returns:
        list[CompetencyAssessment]: the assessments created, one per changed competency.
    """
    return [record_level(submission, link, level, assessed_by) for link, level in level_changes(submission, data)]


def self_assessment_links(submission):
    """ The quest's competency links its student is asked to self-assess on handing it in: the ones an
    approval records evidence for, when the deck has competencies enabled and the quest asks for a
    self-assessment.

    Args:
        submission (QuestSubmission): the submission being handed in.

    Returns:
        list[QuestCompetency]: the links (empty when no self-assessment is asked for).
    """
    if not competencies_enabled() or not submission.quest.competency_self_assessment:
        return []
    return approval_links(submission.quest)


def posted_self_level(data, link):
    """ The level the student chose for their self-assessment in a link's competency. Choosing one is
    optional, so a competency left on "Skip" (or posted anything but a level) has none.

    Args:
        data (QueryDict): the submission form's POST data.
        link (QuestCompetency): the quest's link to the competency.

    Returns:
        int or None: a ProficiencyLevel value, or None.
    """
    try:
        level = int(data.get(self_assessment_field_name(link.competency_id)))
    except (TypeError, ValueError):
        return None
    return level if level in ProficiencyLevel.values else None


def posted_self_assessments(submission, data):
    """ The levels the student chose for their self-assessment on handing the submission in.

    Args:
        submission (QuestSubmission): the submission being handed in.
        data (QueryDict): the submission form's POST data.

    Returns:
        list[tuple[QuestCompetency, int]]: each self-assessed link with the level chosen (those left
        on "Skip" are left out).
    """
    chosen = [(link, posted_self_level(data, link)) for link in self_assessment_links(submission)]
    return [(link, level) for link, level in chosen if level is not None]


def record_self_assessments(submission, chosen):
    """ Record the student's self-assessment of the submission, each level replacing the one they gave
    the competency on an earlier hand-in of it, and leaving the teacher's levels alone.

    Args:
        submission (QuestSubmission): the submission handed in; its student assessed themself.
        chosen (list[tuple[QuestCompetency, int]]): what posted_self_assessments returned.

    Returns:
        list[CompetencyAssessment]: the self-assessments created.
    """
    source_content_type = ContentType.objects.get_for_model(submission)
    recorded = []
    for link, level in chosen:
        CompetencyAssessment.objects.self_assessments().filter(
            source_content_type=source_content_type, source_object_id=submission.pk, competency=link.competency,
        ).delete()
        assessment = CompetencyAssessment(
            user=submission.user,
            competency=link.competency,
            level=level,
            source_content_type=source_content_type,
            source_object_id=submission.pk,
            assessed_by=submission.user,
        )
        assessment.full_clean()
        assessment.save()
        recorded.append(assessment)
    return recorded


def describe_self_assessments(chosen):
    """ The student's self-assessment, one line per competency, for the comment they hand the quest in
    with, as the other choices they make on the form are listed there. A long name is cut short.

    Args:
        chosen (list[tuple[QuestCompetency, int]]): what posted_self_assessments returned.

    Returns:
        list[str]: plain text lines, e.g. "Self-assessment of Choose a design opportunity: Proficient".
    """
    labels = SiteConfig.get().get_competency_scale_labels()
    return [f"Self-assessment of {truncatechars(link.competency.name, 50)}: {labels[level]}" for link, level in chosen]


def assessments_comment_html(assessments):
    """ The competency levels an approval or comment recorded, for the comment itself, so the student
    reads them in the conversation alongside the approval (as a granted badge is announced there),
    and the conversation keeps each rating given. A long name is cut short, with the full name in
    its title.

    Args:
        assessments (list[CompetencyAssessment]): what record_approval_assessments or
            record_level_changes returned.

    Returns:
        str: safe HTML listing each competency with the deck's label for its level, or '' for none.
    """
    if not assessments:
        return ''
    labels = SiteConfig.get().get_competency_scale_labels()
    items = format_html_join('', '<li><span title="{}">{}</span>: <b>{}</b></li>', (
        (assessment.competency.qualified_name, truncatechars(assessment.competency.name, 50), labels[assessment.level])
        for assessment in assessments
    ))
    return format_html('<p>Competencies:</p><ul>{}</ul>', items)
