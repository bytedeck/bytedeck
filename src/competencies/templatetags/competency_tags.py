from django import template

from siteconfig.models import SiteConfig

from ..assessments import approval_links
from ..forms import competency_level_field_name
from ..models import ProficiencyLevel

register = template.Library()


@register.inclusion_tag('competencies/snippets/approval_levels.html')
def competency_approval_levels(submission):
    """ The competency level controls for a submission's approval form: one per competency the
    quest gives evidence of, pre-selected to the link's default level and labelled with the
    deck's proficiency scale. Renders nothing when the deck has competencies disabled or the quest
    has no active competencies.

    Reads ``submission.quest.quest_competencies``, so a page with many submissions should prefetch
    ``quest__quest_competencies``.

    Args:
        submission (QuestSubmission): the submission the approval form acts on.

    Returns:
        dict: the snippet's context: 'rows', each with the competency, the posted field's name and
        its (level, label, selected) choices; the deck's label for the lowest level; and whether any
        row starts on it (so the nudge shows from the first render, not only once a level changes).
    """
    config = SiteConfig.get()
    if config is None or not config.enable_competencies:
        return {'rows': []}

    labels = config.get_competency_scale_labels()
    rows = [
        {
            'competency': link.competency,
            'field_name': competency_level_field_name(link.competency_id),
            'levels': [(level, labels[level], level == link.default_level) for level in ProficiencyLevel.values],
        }
        for link in approval_links(submission.quest)
    ]
    starts_on_lowest = any(selected for row in rows for level, _label, selected in row['levels'] if level == ProficiencyLevel.EMERGING)
    return {'rows': rows, 'lowest_label': labels[ProficiencyLevel.EMERGING], 'starts_on_lowest': starts_on_lowest}
