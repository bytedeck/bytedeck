"""Recording competency evidence when a quest submission is approved.

Approving a submission of a quest with competencies attached records one CompetencyAssessment
per competency: the level the teacher chose on the approval form, or the link's default level
when none was posted (quick approvals, and quests that need no teacher approval at all). Each
approval records new rows, so a submission approved again after being returned adds to the
student's history rather than replacing it.
"""

from django.contrib.contenttypes.models import ContentType
from django.template.defaultfilters import truncatechars
from django.utils.html import format_html, format_html_join

from siteconfig.models import SiteConfig

from .forms import competency_level_field_name
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


def posted_level(data, link):
    """ The level posted for a link's competency on the approval form, or the link's default.

    Args:
        data (QueryDict or None): the approval form's POST data, or None when no form was posted.
        link (QuestCompetency): the quest's link to the competency.

    Returns:
        int: a ProficiencyLevel value. Anything posted that isn't one (a hand-made request) falls
        back to the default, as a missing value does.
    """
    raw = (data or {}).get(competency_level_field_name(link.competency_id))
    try:
        level = int(raw)
    except (TypeError, ValueError):
        return link.default_level
    return level if level in ProficiencyLevel.values else link.default_level


def record_approval_assessments(submission, assessed_by=None, data=None):
    """ Record the competency evidence an approval of the submission gives, if the deck has
    competencies enabled.

    Args:
        submission (QuestSubmission): the submission just approved; its student is the one assessed.
        assessed_by (User or None): the teacher who approved it, or None for a quest that is
            approved automatically (system-assessed).
        data (QueryDict or None): the approval form's POST data, for the levels the teacher chose.

    Returns:
        list[CompetencyAssessment]: the assessments created, one per competency (empty when the
        flag is off or the quest has no active competencies).
    """
    config = SiteConfig.get()
    if config is None or not config.enable_competencies:
        return []

    source_content_type = ContentType.objects.get_for_model(submission)
    assessments = []
    for link in approval_links(submission.quest):
        assessment = CompetencyAssessment(
            user=submission.user,
            competency=link.competency,
            level=posted_level(data, link),
            source_content_type=source_content_type,
            source_object_id=submission.pk,
            assessed_by=assessed_by,
        )
        assessment.full_clean()
        assessment.save()
        assessments.append(assessment)
    return assessments


def assessments_comment_html(assessments):
    """ The competency levels an approval recorded, for the comment that approves the submission,
    so the student reads them in the conversation alongside the approval itself (as a granted badge
    is announced there). A long name is cut short, with the full name in its title.

    Args:
        assessments (list[CompetencyAssessment]): what record_approval_assessments returned.

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
