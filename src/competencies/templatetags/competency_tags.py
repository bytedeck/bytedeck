from django import template
from django.contrib.contenttypes.models import ContentType

from siteconfig.models import SiteConfig

from ..assessments import approval_links, posted_level
from ..forms import competency_level_field_name
from ..models import CompetencyAssessment, ProficiencyLevel

register = template.Library()


@register.inclusion_tag('competencies/snippets/approval_levels.html', takes_context=True)
def competency_approval_levels(context, submission):
    """ The competency level controls for a submission's approval form: one per competency the
    quest gives evidence of, labelled with the deck's proficiency scale. Each starts on the link's
    default level, or, when the page is re-rendered for a posted form that didn't validate, on the
    level the teacher posted, so resubmitting it records their choice rather than the default.
    Renders nothing when the deck has competencies disabled or the quest has no active competencies.

    Reads ``submission.quest.quest_competencies``, so a page with many submissions should prefetch
    ``quest__quest_competencies``.

    Args:
        context (Context): the template context, for the request whose POST holds any posted levels.
        submission (QuestSubmission): the submission the approval form acts on.

    Returns:
        dict: the snippet's context: 'rows', each with the competency, the posted field's name and
        its (level, label, selected) choices; the deck's label for the lowest level; and whether any
        row starts on it (so the nudge shows from the first render, not only once a level changes).
    """
    config = SiteConfig.get()
    if config is None or not config.enable_competencies:
        return {'rows': []}

    request = context.get('request')
    data = request.POST if request is not None and request.method == 'POST' else None
    labels = config.get_competency_scale_labels()
    rows = []
    for link in approval_links(submission.quest):
        chosen = posted_level(data, link)
        rows.append({
            'competency': link.competency,
            'field_name': competency_level_field_name(link.competency_id),
            'levels': [(level, labels[level], level == chosen) for level in ProficiencyLevel.values],
        })
    starts_on_lowest = any(selected for row in rows for level, _label, selected in row['levels'] if level == ProficiencyLevel.EMERGING)
    return {'rows': rows, 'lowest_label': labels[ProficiencyLevel.EMERGING], 'starts_on_lowest': starts_on_lowest}


@register.inclusion_tag('competencies/snippets/quest_competency_chips.html', takes_context=True)
def quest_competency_chips(context, quest, submission=None):
    """ A quest's competencies as chips for its Quest Info list.

    On a submission's page, a competency assessed when that submission was approved shows the
    level recorded for it, coloured by level (the latest, if it was approved again after a return),
    so the student sees how their work on this quest was assessed. Otherwise staff see each
    competency's default level and students see its name, so they know what the quest gives
    evidence of.

    Args:
        context (Context): the template context, for the viewing user.
        quest (Quest): the quest whose competencies to list.
        submission (QuestSubmission, optional): the submission the page shows, if any.

    Returns:
        dict: the snippet's context: 'chips', each with the competency's name and, when it has
        one, the 'label' to show after it and the recorded 'level' that colours it.
    """
    recorded = {}
    if submission:
        assessments = CompetencyAssessment.objects.filter(
            source_content_type=ContentType.objects.get_for_model(submission), source_object_id=submission.pk,
        ).order_by('-timestamp', '-pk')
        for assessment in assessments:
            recorded.setdefault(assessment.competency_id, assessment.level)

    request = context.get('request')
    is_staff = request is not None and request.user.is_staff
    labels = SiteConfig.get().get_competency_scale_labels()
    chips = []
    for link in quest.quest_competencies.all():
        level = recorded.get(link.competency_id)
        if level:
            chips.append({'name': link.competency.name, 'label': labels[level], 'level': level})
        elif is_staff:
            chips.append({'name': link.competency.name, 'label': labels[link.default_level]})
        else:
            chips.append({'name': link.competency.name})
    return {'chips': chips}
