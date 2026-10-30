from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class ProficiencyLevel(models.IntegerChoices):
    """ The BC 4-point proficiency scale: https://curriculum.gov.bc.ca/

    Levels are stored as integers so that aggregation and comparison are trivial.
    The labels here are fallbacks; each deck can customize the displayed labels
    via SiteConfig (see SiteConfig.get_competency_scale_labels).
    """
    EMERGING = 1, 'Emerging'
    DEVELOPING = 2, 'Developing'
    PROFICIENT = 3, 'Proficient'
    EXTENDING = 4, 'Extending'


class RollupStrategy(models.TextChoices):
    """ How a student's assessments of a competency become their current level in it: the deck's
    choice (SiteConfig.competency_rollup), applied by competencies.rollup. """
    MOST_RECENT = 'most_recent', 'Most recent assessment'
    MOST_COMMON = 'most_common', 'Most common level in the latest assessments'
    HIGHEST = 'highest', 'Highest level assessed'


class CompetencyQuerySet(models.QuerySet):
    """ Custom queryset for Competency, exposing the common filters as chainable methods. """

    def active(self):
        """ Returns the queryset filtered down to active (not soft-deleted) competencies. """
        return self.filter(active=True)


class Competency(models.Model):
    """ A deck-level library of competencies (learning standards) that can be attached to quests
    and assessed on the 4-point proficiency scale.
    """

    name = models.CharField(max_length=255)

    description = models.TextField(
        blank=True,
        help_text="An optional elaboration or full text of this competency."
    )

    category = models.CharField(
        max_length=255, blank=True,
        help_text="A free-text strand or grouping, e.g. \"Curricular Competency\", \"Big Idea\", or \"Core Competency\"."
    )

    # db_default as well as default: during a deploy the outgoing version still inserts competencies
    # without this column, so the database has to fill it in (CONTRIBUTING.md, "Migrations and the
    # deploy window").
    course = models.CharField(
        max_length=255, blank=True, default='', db_default='',
        help_text="The course this competency comes from, e.g. \"ADST 9\", or \"Core\" for the BC Core Competencies. "
                  "Competency pickers show it before the category, e.g. \"ADST 9: Defining: Choose a design opportunity\"."
    )

    source_id = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="A stable identifier into a source taxonomy such as the BC curriculum. "
                  "Used to de-duplicate imports and to match competencies across decks."
    )

    active = models.BooleanField(
        default=True,
        help_text="Instead of deleting a competency, deactivate it to hide it from new use "
                  "while preserving existing assessment evidence. A competency that is referenced "
                  "by assessment evidence cannot be deleted."
    )

    objects = CompetencyQuerySet.as_manager()

    class Meta:
        ordering = ['course', 'category', 'name']
        verbose_name_plural = 'competencies'

    def __str__(self):
        """ Returns the competency's name. """
        return self.name

    @property
    def course_and_category(self):
        """ Where the competency sits: its course and category, e.g. "Core: Communication" (either
        part left out when blank, so possibly ''). """
        return ": ".join(part for part in (self.course, self.category) if part)

    @property
    def qualified_name(self):
        """ The name with its course and category in front, e.g. "Core: Communication: Collaborating",
        so competencies from different courses can be told apart in a picker. """
        return ": ".join(part for part in (self.course_and_category, self.name) if part)


class QuestCompetencyManager(models.Manager):
    """ Default manager for QuestCompetency, so related managers such as quest.quest_competencies
    use it too. A link is nearly always shown by its competency's name, and the default ordering
    joins the competency anyway, so it is loaded in the same query.
    """

    def get_queryset(self):
        """ Returns the links with their competencies selected in the same query. """
        return super().get_queryset().select_related('competency')


class QuestCompetency(models.Model):
    """ Through-table linking a Quest to a Competency, carrying the default proficiency level
    that approving a submission of this quest generally demonstrates.
    """

    quest = models.ForeignKey(
        'quest_manager.Quest', on_delete=models.CASCADE, related_name='quest_competencies'
    )

    competency = models.ForeignKey(
        Competency, on_delete=models.CASCADE, related_name='quest_competencies'
    )

    default_level = models.IntegerField(
        choices=ProficiencyLevel.choices, default=ProficiencyLevel.PROFICIENT,
        help_text="The proficiency level that completing this quest generally demonstrates. "
                  "Teachers can adjust the level for individual students when approving submissions."
    )

    objects = QuestCompetencyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['quest', 'competency'], name='unique_quest_competency')
        ]
        ordering = ['competency__course', 'competency__category', 'competency__name']
        verbose_name_plural = 'quest competencies'

    def __str__(self):
        """ Returns "<quest> - <competency>", identifying both ends of the link. """
        return f"{self.quest} - {self.competency}"


class CompetencyAssessment(models.Model):
    """ The atomic evidence record: a single assessment of a student on a single competency,
    at a specific level, from a specific source (a QuestSubmission in v1; the generic FK allows
    badges, portfolios, self-assessments, etc. to produce evidence later).

    Evidence is intended to outlive its source: deleting a Quest (which cascades to its
    submissions) must NOT delete assessments. The generic FK simply dangles (source_object
    resolves to None) and the evidence record remains.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='competency_assessments',
        help_text="The student being assessed."
    )

    competency = models.ForeignKey(
        # PROTECT: a competency referenced by evidence can be deactivated but never hard-deleted.
        Competency, on_delete=models.PROTECT, related_name='assessments'
    )

    level = models.IntegerField(choices=ProficiencyLevel.choices)

    source_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='competency_assessments'
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('source_content_type', 'source_object_id')

    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='competency_assessments_given',
        help_text="The staff user who made this assessment. Null means self- or system-assessed."
    )

    note = models.TextField(blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'competency', 'timestamp'], name='competency_evidence_idx')
        ]

    def clean(self):
        """ Validates that the generic source FK is set atomically: either both
        source_content_type and source_object_id are provided (evidence with a source)
        or neither is (source-less evidence, e.g. a manual teacher assessment).

        This is model-level validation only, deliberately not a database constraint:
        source_content_type is SET_NULL, so deleting a stale ContentType row (e.g. via
        remove_stale_contenttypes after an app is removed) legitimately leaves the id
        half behind at the database level, and a both-or-neither check constraint would
        turn that cleanup into an IntegrityError.

        Raises:
            ValidationError: if exactly one half of the source pair is set.
        """
        super().clean()
        if (self.source_content_type is None) != (self.source_object_id is None):
            raise ValidationError(
                "The evidence source must be set atomically: provide both "
                "source_content_type and source_object_id, or neither."
            )

    def __str__(self):
        """ Returns "<student>: <competency> = <level label>" for admin and debugging output. """
        return f"{self.user}: {self.competency} = {self.get_level_display()}"


class CompetencyOverrideQuerySet(models.QuerySet):
    """ Custom queryset for CompetencyOverride. """

    def in_force(self):
        """ The overrides that stand: for each student and competency in this queryset, its latest
        record (ties on the timestamp going to the one recorded last), unless that record cleared the
        override.

        It is one query: the latest record per student and competency is picked by a Postgres
        ``DISTINCT ON`` subquery.

        Returns:
            QuerySet: at most one override per student and competency, each with a level.
        """
        latest = self.order_by('user_id', 'competency_id', '-timestamp', '-pk').distinct('user_id', 'competency_id')
        return self.filter(pk__in=latest.values('pk')).exclude(level=None)


class CompetencyOverride(models.Model):
    """ A teacher's summative level for a student in a competency, which stands as the student's
    current level in it in place of the roll-up of their evidence (see competencies.rollup), on
    every page that shows one.

    Each change is a new record, so who set which level, when and why stays on record: a student's
    latest record for a competency is the one in force, and a record with no level clears the
    override, so the roll-up of their evidence applies again.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='competency_overrides',
        help_text="The student whose level it is."
    )

    competency = models.ForeignKey(
        # PROTECT, as for evidence: a competency with a level set can be deactivated but never hard-deleted.
        Competency, on_delete=models.PROTECT, related_name='overrides'
    )

    level = models.IntegerField(
        choices=ProficiencyLevel.choices, null=True, blank=True,
        help_text="The level that stands as the student's current level in the competency, "
                  "or blank to clear the override."
    )

    note = models.TextField(blank=True, help_text="Why it was set or cleared. Only staff see it.")

    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='competency_overrides_set',
        help_text="The staff user who set or cleared it."
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    objects = CompetencyOverrideQuerySet.as_manager()

    class Meta:
        ordering = ['-timestamp', '-pk']
        indexes = [
            models.Index(fields=['user', 'competency', 'timestamp'], name='competency_override_idx')
        ]

    def __str__(self):
        """ Returns "<student>: <competency> set to <level label>", or "... cleared", for admin and debugging output. """
        if self.level is None:
            return f"{self.user}: {self.competency} cleared"
        return f"{self.user}: {self.competency} set to {self.get_level_display()}"
