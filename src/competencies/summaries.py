"""A student's competencies course by course: the course averages on their profile, and every
assessment of every competency on their competencies summary page.

A course's competencies are those carrying its official course label (Competency.course). The courses
shown for a student are the courses they are registered in this semester that have chosen a
competency set (Course.competency_set), whether or not they have been assessed in them yet, plus any
other set they have a level in (e.g. the BC Core Competencies, which no course chooses as its set),
from evidence or a teacher's override. Within a course, the competencies counted are its active
ones, plus any deactivated ones the student already has a level in.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import groupby

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import Q
from django.utils.text import slugify

from courses.models import CourseStudent
from quest_manager.models import QuestSubmission

from .models import Competency, CompetencyAssessment, ProficiencyLevel
from .rollup import current_levels


#: The three-letter code shown for each level on a chip where many share a row (see level_codes).
DEFAULT_LEVEL_CODES = {
    ProficiencyLevel.EMERGING: "EMG",
    ProficiencyLevel.DEVELOPING: "DEV",
    ProficiencyLevel.PROFICIENT: "PRF",
    ProficiencyLevel.EXTENDING: "EXT",
}


def level_codes(labels):
    """ A three-letter code for each level of the deck's Proficiency Scale, for chips where many share a
    row: the level's default code (EMG, DEV, PRF, EXT) while the deck uses the level's default label,
    else the first three letters or digits of the deck's own label, uppercased (or the default code
    when its label has none), so the code still matches what the deck calls the level.

    Args:
        labels (dict[int, str]): the deck's label for each level (SiteConfig.get_competency_scale_labels).

    Returns:
        dict[int, str]: each level's code.
    """
    codes = {}
    for level, label in labels.items():
        own = re.sub(r'[\W_]', '', label)[:3].upper()
        codes[level] = own if label != ProficiencyLevel(level).label and own else DEFAULT_LEVEL_CODES[level]
    return codes


#: The averages (out of 4) that round to each level (see CourseCompetencies.level), 0 being no level yet.
LEVEL_RANGES = {
    0: "under 0.5",
    1: "0.5 to under 1.5",
    2: "1.5 to under 2.5",
    3: "2.5 to under 3.5",
    4: "3.5 to 4",
}


@dataclass
class CourseCompetencies:
    """ One course's competencies for a student, with the student's current level in each.

    Attributes:
        label (str): the official course label, e.g. "ADST 9" ('' for competencies with none).
        registration (CourseStudent or None): the student's registration in a course that chose this
            set, or None for a set they have evidence in outside their courses.
        competencies (list[Competency]): the course's competencies, in category and name order.
        levels (dict[int, int]): competency pk to the student's current level, for those with one.
        overrides (dict[int, CompetencyOverride]): competency pk to the teacher's override in force,
            for those whose current level a teacher has set.
    """
    label: str
    registration: object = None
    competencies: list = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    overrides: dict = field(default_factory=dict)

    @property
    def title(self):
        """ The course's name: the title of the student's course, else the set's label. """
        if self.registration is not None:
            return self.registration.course.title
        return self.label or "Other competencies"

    @property
    def pane_id(self):
        """ The HTML id of the course's tab on the competencies summary, which the profile links to. """
        if self.registration is not None:
            return f"course-pane-{self.registration.pk}"
        return f"course-pane-{slugify(self.label) or 'other'}"

    @property
    def course_levels(self):
        """ The student's current level in each of the course's competencies they have been assessed in. """
        return [self.levels[competency.pk] for competency in self.competencies if competency.pk in self.levels]

    @property
    def total(self):
        """ The sum of the student's current levels across the course's competencies (unassessed ones adding 0). """
        return sum(self.course_levels)

    @property
    def average(self):
        """ The mean of the student's current level in each of the course's competencies, out of 4,
        counting a competency not assessed yet as 0 (and 0 for a course with no competencies). """
        if not self.competencies:
            return 0
        return self.total / len(self.competencies)

    @property
    def level(self):
        """ The average as a point on the scale: rounded to the nearest level, halves up, so 2.5 is
        level 3. Below 0.5 it is 0, which is no level at all. """
        return math.floor(self.average + 0.5)


def course_competencies(student):
    """ The student's competencies, course by course: first each of their current courses that has a
    competency set, then each other set they have evidence in, by label.

    Current levels come from the roll-up (competencies.rollup.current_levels), and a set the student
    has a level in only through a teacher's override shows too. It takes four queries, however many
    courses and competencies there are.

    Args:
        student (User): the student.

    Returns:
        list[CourseCompetencies]: one per course whose set has at least one competency.
    """
    levels, overrides = current_levels(user=student)
    levels, overrides = levels[student.pk], overrides[student.pk]
    registrations = [
        registration for registration in CourseStudent.objects.current_courses(student).select_related('course', 'block')
        if registration.course.competency_set
    ]
    registered_labels = {registration.course.competency_set for registration in registrations}
    # the sets the student has a level in, read in the same query as the competencies
    assessed_labels = Competency.objects.filter(pk__in=list(levels)).values('course')

    competencies = Competency.objects.filter(
        Q(course__in=registered_labels) | Q(course__in=assessed_labels)
    ).filter(Q(active=True) | Q(pk__in=list(levels)))
    by_label = {label: list(group) for label, group in groupby(competencies, key=lambda competency: competency.course)}

    courses = [
        CourseCompetencies(registration.course.competency_set, registration, by_label[registration.course.competency_set], levels, overrides)
        for registration in registrations if registration.course.competency_set in by_label
    ]
    courses += [CourseCompetencies(label, None, by_label[label], levels, overrides) for label in by_label if label not in registered_labels]
    return courses


def course_matrix(course, block=None):
    """ A course's students by its competencies, for the staff competency matrix: each student
    registered in the course in an open semester (students only, not staff or test accounts, and only
    active users), optionally in one block, by last name, with their current level in each competency
    of the course's set.

    Each row is the same CourseCompetencies the student's own competencies page shows for the course,
    so its average and current level of proficiency match it: the set's active competencies, plus any
    deactivated ones that student has a level in. The columns are the set's active competencies plus
    any deactivated ones some row has a level in.

    It takes four queries, however many students and competencies there are.

    Args:
        course (Course): the course, which has a competency set.
        block (Block or None): only the students in this block, or None for all of them.

    Returns:
        tuple: the columns (list[Competency], in category and name order) and the rows
        (list[CourseCompetencies], one per registration).
    """
    registrations = CourseStudent.objects.get_queryset().in_open_semesters().get_students_only().filter(course=course, user__is_active=True)
    if block is not None:
        registrations = registrations.filter(block=block)
    registrations = list(registrations.select_related('user__profile', 'block').order_by('user__last_name', 'user__first_name', 'user__username'))

    levels, overrides = current_levels(
        user_id__in=[registration.user_id for registration in registrations], competency__course=course.competency_set,
    )
    assessed = {competency_id for student_levels in levels.values() for competency_id in student_levels}

    columns = list(Competency.objects.filter(course=course.competency_set).filter(Q(active=True) | Q(pk__in=assessed)))
    rows = [
        CourseCompetencies(
            course.competency_set,
            registration,
            [competency for competency in columns if competency.active or competency.pk in levels[registration.user_id]],
            levels[registration.user_id],
            overrides[registration.user_id],
        )
        for registration in registrations
    ]
    return columns, rows


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
