from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
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


class CompetencyQuerySet(models.QuerySet):

    def active(self):
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
        ordering = ['category', 'name']
        verbose_name_plural = 'competencies'

    def __str__(self):
        return self.name


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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['quest', 'competency'], name='unique_quest_competency')
        ]
        verbose_name_plural = 'quest competencies'

    def __str__(self):
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

    def __str__(self):
        return f"{self.user}: {self.competency} = {self.get_level_display()}"
