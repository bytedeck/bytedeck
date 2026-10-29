from django import template

from siteconfig.models import SiteConfig

from ..assessments import (
    approval_links, posted_level, posted_self_level, self_assessment_links, starting_level, submission_levels, submission_self_levels,
)
from ..forms import competency_level_field_name, self_assessment_field_name
from ..models import ProficiencyLevel
from ..summaries import course_competencies

register = template.Library()


@register.inclusion_tag('competencies/snippets/quest_competency_list.html')
def quest_competency_list(quest):
    """ The competencies line of a quest's Quest Info: the competencies its approval records evidence
    for, so a deactivated competency still linked to the quest isn't listed when approving it would
    record no level for it. Renders nothing when there are none.

    Args:
        quest (Quest): the quest the Quest Info describes.

    Returns:
        dict: the snippet's context: 'links', the quest's links to its active competencies.
    """
    return {'links': approval_links(quest)}


@register.simple_tag
def course_competency_averages(student):
    """ The student's competency average in each of their current courses that has a competency set
    (see competencies.summaries), for the profile to show beside each course's XP: worked out once for
    the page, in the same few queries however many courses and competencies there are.

    Args:
        student (User): the student whose profile it is.

    Returns:
        dict: registration pk to a dict of the course's CourseCompetencies and the deck's label for its
        average level ('' below the scale). Empty when the deck has competencies disabled.
    """
    config = SiteConfig.get()
    if config is None or not config.enable_competencies:
        return {}

    labels = config.get_competency_scale_labels()
    return {
        course.registration.pk: {'course': course, 'level_label': labels.get(course.level, '')}
        for course in course_competencies(student) if course.registration is not None
    }


@register.inclusion_tag('competencies/snippets/course_competency_average.html')
def course_competency_average(averages, registration):
    """ A course's competency level beside its XP on the profile, linked to the course's tab on the
    student's competencies summary, which explains how it is worked out. Renders nothing for a course
    without a competency set, or when the deck has competencies disabled.

    Args:
        averages (dict): what course_competency_averages returned for the student.
        registration (CourseStudent): the course registration the XP bar is for.

    Returns:
        dict: the snippet's context: 'average', the course's entry in averages, or None.
    """
    return {'average': averages.get(registration.pk)}


@register.inclusion_tag('competencies/snippets/approval_levels.html', takes_context=True)
def competency_approval_levels(context, submission):
    """ The competency level controls for a submission's approval form: one per competency the
    quest gives evidence of, labelled with the deck's proficiency scale. Approving records them; on an
    approved submission, commenting records the ones changed. Each starts on the submission's current
    level (from an earlier approval) or else the link's default, or, when the page is re-rendered for
    a posted form that didn't validate, on the level the teacher posted, so resubmitting it records
    their choice. Renders nothing when the deck has competencies disabled or the quest has no active
    competencies.

    Reads ``submission.quest.quest_competencies`` and the submission's current levels, so a page with
    many submissions should prefetch ``quest__quest_competencies`` and call
    competencies.assessments.prefetch_submission_levels.

    Args:
        context (Context): the template context, for the request whose POST holds any posted levels.
        submission (QuestSubmission): the submission the approval form acts on.

    Returns:
        dict: the snippet's context: 'rows', each with the competency, the posted field's name and
        its (level, label, selected) choices; whether the submission is approved; the deck's label
        for the lowest level; and whether any row starts on it (so the nudge shows from the first
        render, not only once a level changes).
    """
    config = SiteConfig.get()
    if config is None or not config.enable_competencies:
        return {'rows': []}

    request = context.get('request')
    data = request.POST if request is not None and request.method == 'POST' else None
    labels = config.get_competency_scale_labels()
    links = approval_links(submission.quest)
    current = submission_levels(submission) if links else {}
    rows = []
    for link in links:
        chosen = posted_level(data, link, starting_level(link, current))
        rows.append({
            'competency': link.competency,
            'field_name': competency_level_field_name(link.competency_id),
            'levels': [(level, labels[level], level == chosen) for level in ProficiencyLevel.values],
        })
    starts_on_lowest = any(selected for row in rows for level, _label, selected in row['levels'] if level == ProficiencyLevel.EMERGING)
    return {
        'rows': rows,
        'approved': submission.is_approved,
        'lowest_label': labels[ProficiencyLevel.EMERGING],
        'starts_on_lowest': starts_on_lowest,
    }


@register.inclusion_tag('competencies/snippets/self_assessment.html', takes_context=True)
def competency_self_assessment(context, submission):
    """ The student's self-assessment controls on their submission form, when the quest asks for one:
    one per competency the quest gives evidence of, labelled with the deck's proficiency scale, with
    "Skip" first since a self-assessment is optional. Each starts on the level the student chose on an
    earlier hand-in of the submission (one returned to them), or else on "Skip", or, when the page is
    re-rendered for a posted form that didn't validate, on the level they posted. Renders nothing when
    the deck has competencies disabled or the quest doesn't ask for a self-assessment.

    Args:
        context (Context): the template context, for the request.
        submission (QuestSubmission): the student's submission.

    Returns:
        dict: the snippet's context: 'rows', each with the competency, its field name, the levels as
        (level, label, selected), and 'skipped' when none is selected.
    """
    links = self_assessment_links(submission)
    if not links:
        return {'rows': []}
    labels = SiteConfig.get().get_competency_scale_labels()
    request = context.get('request')
    posted = request.POST if request is not None and request.method == 'POST' else None
    earlier = submission_self_levels(submission) if posted is None else {}
    rows = []
    for link in links:
        chosen = posted_self_level(posted, link) if posted is not None else earlier.get(link.competency_id)
        rows.append({
            'competency': link.competency,
            'field_name': self_assessment_field_name(link.competency_id),
            'levels': [(level, labels[level], level == chosen) for level in ProficiencyLevel.values],
            'skipped': chosen is None,
        })
    return {'rows': rows}
