from django import template

from siteconfig.models import SiteConfig

from ..assessments import approval_links, posted_level
from ..forms import competency_level_field_name
from ..models import ProficiencyLevel

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
