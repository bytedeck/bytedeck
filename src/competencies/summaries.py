"""A student's competencies course by course: the course averages on their profile, and every
assessment of every competency on their competencies summary page.

A course's competencies are those carrying its official course label (Competency.course). The courses
shown for a student are the competency sets of the courses they are registered in this semester
(Course.competency_set), whether or not they have been assessed in them yet, plus any other course
label they have evidence in (e.g. the BC Core Competencies, which no course chooses as its set).
Within a course, the competencies counted are its active ones, plus any deactivated ones the student
already has evidence for.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import groupby

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import Q

from courses.models import CourseStudent
from quest_manager.models import QuestSubmission

from .models import Competency, CompetencyAssessment


@dataclass
class CourseCompetencies:
    """ One course's competencies for a student, with the student's current level in each.

    Attributes:
        label (str): the official course label, e.g. "ADST 9" ('' for competencies with none).
        course_titles (list[str]): the titles of the student's current courses that chose this set,
            leaving out one titled the same as the set (which would only repeat the label).
        competencies (list[Competency]): the course's competencies, in category and name order.
        levels (dict[int, int]): competency pk to the student's current level, for those assessed.
    """
    label: str
    course_titles: list = field(default_factory=list)
    competencies: list = field(default_factory=list)
    levels: dict = field(default_factory=dict)

    @property
    def average(self):
        """ The mean of the student's current level in each of the course's competencies, out of 4,
        counting a competency not assessed yet as 0. """
        return sum(self.levels.get(competency.pk, 0) for competency in self.competencies) / len(self.competencies)

    @property
    def level(self):
        """ The average as a point on the scale: rounded to the nearest level, halves up, so 2.5 is
        level 3. Below 0.5 it is 0, which is no level at all. """
        return math.floor(self.average + 0.5)


def course_competencies(student):
    """ The student's competencies, course by course (see the module docstring for which courses).

    Current levels come from the roll-up (CompetencyAssessmentQuerySet.current). It takes three
    queries, however many courses and competencies there are.

    Args:
        student (User): the student.

    Returns:
        list[CourseCompetencies]: one per course with at least one competency, in course label order.
    """
    current = CompetencyAssessment.objects.filter(user=student).current().select_related('competency')
    levels = {assessment.competency_id: assessment.level for assessment in current}
    labels = {assessment.competency.course for assessment in current}

    titles = defaultdict(list)
    for registration in CourseStudent.objects.current_courses(student).select_related('course').order_by('course__title'):
        course = registration.course
        if course.competency_set:
            labels.add(course.competency_set)
            if course.title != course.competency_set:
                titles[course.competency_set].append(course.title)

    competencies = Competency.objects.filter(course__in=labels).filter(Q(active=True) | Q(pk__in=list(levels)))
    return [
        CourseCompetencies(
            label=label,
            course_titles=titles.get(label, []),
            competencies=list(group),
            levels=levels,
        )
        for label, group in groupby(competencies, key=lambda competency: competency.course)
    ]


@dataclass
class Evidence:
    """ One assessment as evidence: where it came from, as a description and a link when it has one.

    Attributes:
        assessment (CompetencyAssessment): the assessment.
        description (str): what it was given for, e.g. the quest's name.
        url (str or None): the page of the work it was given for, when that still exists and has one.
    """
    assessment: CompetencyAssessment
    description: str
    url: str = None


def evidence_by_competency(student):
    """ Every assessment of the student, oldest first, grouped by competency, each with what it was
    given for: a quest submission links to the submission and is described by its quest's name; any
    other source links to its own page, when it has one. Evidence whose submission is gone says its
    quest was deleted, and evidence with no source, or whose other source is gone, has no link.

    The sources are prefetched, a submission's through the base manager so that submissions of quests
    since archived or unpublished still name their quest, so the queries don't grow with the evidence.

    Args:
        student (User): the student.

    Returns:
        dict[int, list[Evidence]]: competency pk to its evidence, oldest first.
    """
    submission_type_id = ContentType.objects.get_for_model(QuestSubmission).pk
    assessments = CompetencyAssessment.objects.filter(user=student).order_by('timestamp', 'pk').prefetch_related(
        GenericPrefetch('source_object', [QuestSubmission._base_manager.select_related('quest')]),
    )
    evidence = defaultdict(list)
    for assessment in assessments:
        source = assessment.source_object
        if source is None:
            from_quest = assessment.source_content_type_id == submission_type_id
            item = Evidence(assessment, "A deleted quest" if from_quest else "No linked evidence")
        elif assessment.source_content_type_id == submission_type_id:
            item = Evidence(assessment, source.quest.name, source.get_absolute_url())
        else:
            get_url = getattr(source, 'get_absolute_url', None)
            item = Evidence(assessment, str(source), get_url() if get_url else None)
        evidence[assessment.competency_id].append(item)
    return evidence
