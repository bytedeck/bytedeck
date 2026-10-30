"""The roll-up: how a student's assessments of a competency become their current level in it.

Every page that shows a current level (the course levels on a student's profile, their competencies
page, and the staff competency matrix with its CSV) reads it through current_levels, so the deck's
roll-up strategy (SiteConfig.competency_rollup) changes them all alike, and a level a teacher has set
(a CompetencyOverride) stands in place of the roll-up on all of them.
"""

from collections import Counter, defaultdict

from siteconfig.models import SiteConfig

from .models import CompetencyAssessment, CompetencyOverride, RollupStrategy


def roll_up(levels, strategy, count):
    """ One current level from a student's assessments of a competency, by a roll-up strategy:

    - most recent: the level of the latest assessment;
    - most common: the level assessed most often among the latest ``count`` assessments, a tie going
      to whichever of the tied levels was assessed most recently, in keeping with the most recent
      evidence counting for most;
    - highest: the highest level assessed.

    Args:
        levels (list[int]): the levels assessed, oldest first (at least one).
        strategy (str): a RollupStrategy value.
        count (int): how many of the latest assessments the most common level is taken from.

    Returns:
        int: the current level.
    """
    if strategy == RollupStrategy.HIGHEST:
        return max(levels)
    if strategy == RollupStrategy.MOST_COMMON:
        latest = levels[-count:]
        tally = Counter(latest)
        most = max(tally.values())
        return next(level for level in reversed(latest) if tally[level] == most)
    return levels[-1]


def describe_rollup(config):
    """ What a current level is under the deck's roll-up strategy, to follow "which is" in the
    explanations on the competencies pages, e.g. "the level of its most recent assessment".

    Args:
        config (SiteConfig): the deck's settings.

    Returns:
        str: the description.
    """
    if config.competency_rollup == RollupStrategy.HIGHEST:
        return "the highest level it has been assessed at"
    if config.competency_rollup == RollupStrategy.MOST_COMMON:
        return (
            f"the level it was assessed at most often in its latest {config.competency_rollup_count} assessments "
            "(on a tie, whichever of those levels came most recently)"
        )
    return "the level of its most recent assessment"


def evidence_levels(**filters):
    """ Each student's level in each competency they have been assessed in, by the deck's roll-up
    strategy, from the assessments matching the filters: their current level, unless a teacher has
    set one (see current_levels).

    It takes one query, which serves one student's profile or a whole class alike: each student's
    assessments of each competency are read oldest first (ties on the timestamp in the order they
    were recorded) and rolled up here.

    Args:
        **filters: CompetencyAssessment filters choosing the students and competencies, e.g.
            ``user=student`` or ``user_id__in=[...], competency__course="ADST 9"``.

    Returns:
        defaultdict: user pk to a dict of competency pk to the current level, for the competencies
        each has been assessed in (an empty dict for anyone else).
    """
    config = SiteConfig.get()
    assessed = defaultdict(lambda: defaultdict(list))
    assessments = CompetencyAssessment.objects.filter(**filters).order_by('timestamp', 'pk')
    for user_id, competency_id, level in assessments.values_list('user_id', 'competency_id', 'level'):
        assessed[user_id][competency_id].append(level)

    levels = defaultdict(dict)
    for user_id, competencies in assessed.items():
        for competency_id, history in competencies.items():
            levels[user_id][competency_id] = roll_up(history, config.competency_rollup, config.competency_rollup_count)
    return levels


def current_levels(**filters):
    """ Each student's current level in each competency: the level a teacher has set for them, where
    there is an override in force, else the roll-up of their evidence (evidence_levels).

    It takes two queries, however many students and competencies there are.

    Args:
        **filters: filters choosing the students and competencies, which apply to the assessments and
            the overrides alike, e.g. ``user=student`` or ``user_id__in=[...], competency__course="ADST 9"``.

    Returns:
        tuple: the levels (a defaultdict of user pk to a dict of competency pk to the current level,
        for the competencies each has a level in), and the overrides in force (a defaultdict of user
        pk to a dict of competency pk to the CompetencyOverride, with who set it).
    """
    levels = evidence_levels(**filters)
    overrides = defaultdict(dict)
    for override in CompetencyOverride.objects.filter(**filters).in_force().select_related('set_by__profile'):
        overrides[override.user_id][override.competency_id] = override
        levels[override.user_id][override.competency_id] = override.level
    return levels, overrides
