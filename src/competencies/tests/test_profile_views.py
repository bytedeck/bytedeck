from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel
from competencies.summaries import CourseCompetencies, course_competencies, evidence_by_competency
from competencies.tests.test_approval import set_competencies_flag
from courses.models import Course, CourseStudent, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


def own_query_count(queries):
    """ The queries captured, less django-tenants' per-cursor search path setting (not ours).

    Args:
        queries (CaptureQueriesContext): the captured queries.

    Returns:
        int: how many of them are queries of ours.
    """
    return len([query for query in queries.captured_queries if not query['sql'].startswith('SET search_path')])


class StudentCompetenciesMixin:
    """ A teacher, and a student registered this semester in "Digital Hackerspace", whose competency set
    is ADST 9 (three active competencies and a deactivated one), on a deck with competencies enabled,
    which also has a Core competency. """

    def setUp(self):
        """ Creates the users, the course and registration, and the competencies. """
        set_competencies_flag(True, competency_label_level_3="Got It", competency_label_level_4="Nailed It")
        self.teacher = User.objects.create_user('summary_teacher', first_name="Ada", last_name="Lovelace", is_staff=True)
        self.student = User.objects.create_user('summary_student', first_name="Grace", last_name="Hopper")
        self.semester = SiteConfig.get().active_semester
        self.semester.status = Semester.Status.OPEN
        self.semester.save()
        self.course = baker.make(Course, title="Digital Hackerspace", competency_set="ADST 9")
        baker.make(CourseStudent, user=self.student, course=self.course, semester=self.semester)

        self.defining = baker.make(Competency, course="ADST 9", category="Applied Design - Defining", name="Choose a design opportunity")
        self.ideating = baker.make(Competency, course="ADST 9", category="Applied Design - Ideating", name="Generate potential ideas")
        self.making = baker.make(Competency, course="ADST 9", category="Applied Design - Making", name="Use materials safely")
        self.retired = baker.make(Competency, course="ADST 9", category="Applied Design - Making", name="Retired competency", active=False)
        self.collaborating = baker.make(Competency, course="Core", category="Communication", name="Collaborating")

    def assess(self, competency, level, minutes_ago, source=None, assessed_by=None, user=None):
        """ Records an assessment of the student, stamped the given number of minutes ago.

        Returns:
            CompetencyAssessment: the saved assessment.
        """
        assessment = CompetencyAssessment.objects.create(
            user=user or self.student, competency=competency, level=level, source_object=source, assessed_by=assessed_by,
        )
        CompetencyAssessment.objects.filter(pk=assessment.pk).update(timestamp=timezone.now() - timedelta(minutes=minutes_ago))
        return assessment

    def submission(self, quest_name, **quest_fields):
        """ A submission by the student of a new quest with the given name.

        Returns:
            QuestSubmission: the submission.
        """
        return baker.make(QuestSubmission, user=self.student, quest=baker.make(Quest, name=quest_name, **quest_fields))

    def summary_url(self, student=None):
        """ The competencies summary's URL for a student (this class's by default). """
        return reverse('competencies:summary', args=[(student or self.student).pk])

    def profile_url(self, user=None):
        """ The profile page's URL for a user (this class's student by default). """
        return reverse('profiles:profile_detail', args=[(user or self.student).profile.pk])


class CourseCompetenciesTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for competencies.summaries.course_competencies and CourseCompetencies. """

    def test_course_competencies__a_course_averages_every_competency_counting_unassessed_as_zero(self):
        """ The student's course's set averages the current level of each of its active competencies,
        with 0 for one not assessed yet: Extending (the latest of two), nothing, and Proficient make 7/3 """
        self.assess(self.defining, ProficiencyLevel.DEVELOPING, minutes_ago=30)
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.making, ProficiencyLevel.PROFICIENT, minutes_ago=10)

        [adst] = course_competencies(self.student)

        self.assertEqual(adst.label, "ADST 9")
        self.assertEqual(adst.course_titles, ["Digital Hackerspace"])
        self.assertEqual(adst.competencies, [self.defining, self.ideating, self.making])
        self.assertAlmostEqual(adst.average, 7 / 3)
        self.assertEqual(adst.level, ProficiencyLevel.DEVELOPING)

    def test_course_competencies__a_registered_course_shows_before_any_evidence(self):
        """ A course the student is in shows from the start, at an average of 0 and no level """
        [adst] = course_competencies(self.student)

        self.assertEqual(adst.average, 0)
        self.assertEqual(adst.level, 0)

    def test_course_competencies__other_courses_join_once_assessed(self):
        """ A course label the student isn't registered for joins once they have evidence in it, in label
        order, with no course titles; a course with no competencies at all is left out """
        self.course.competency_set = "Vanished Set"
        self.course.save()
        self.assess(self.collaborating, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.ideating, ProficiencyLevel.PROFICIENT, minutes_ago=5)

        courses = course_competencies(self.student)

        self.assertEqual([(course.label, course.course_titles) for course in courses], [("ADST 9", []), ("Core", [])])
        self.assertEqual(courses[1].average, ProficiencyLevel.EXTENDING)

    def test_course_competencies__a_deactivated_competency_counts_once_assessed(self):
        """ A deactivated competency is left out of its course, unless the student already has evidence for it """
        self.assess(self.retired, ProficiencyLevel.PROFICIENT, minutes_ago=5)

        [adst] = course_competencies(self.student)

        self.assertIn(self.retired, adst.competencies)
        self.assertEqual(adst.average, 3 / 4)

    def test_course_competencies__a_course_titled_as_its_set_isnt_repeated(self):
        """ A course titled the same as its competency set adds no title, since it would only repeat the label """
        same_name = baker.make(Course, title="ADST 9", competency_set="ADST 9")
        baker.make(CourseStudent, user=self.student, course=same_name, semester=self.semester)

        [adst] = course_competencies(self.student)

        self.assertEqual(adst.course_titles, ["Digital Hackerspace"])

    def test_course_competencies__a_course_without_a_set_adds_nothing(self):
        """ A course the student is in that hasn't chosen a competency set adds no course """
        baker.make(CourseStudent, user=self.student, course=baker.make(Course, title="Study Hall"), semester=self.semester)

        self.assertEqual([course.label for course in course_competencies(self.student)], ["ADST 9"])

    def test_course_competencies__three_queries(self):
        """ It takes three queries however many courses and competencies there are """
        for competency in (self.defining, self.making, self.collaborating):
            self.assess(competency, ProficiencyLevel.PROFICIENT, minutes_ago=5)

        with CaptureQueriesContext(connection) as queries:
            courses = course_competencies(self.student)
            averages = [course.average for course in courses]

        self.assertEqual(len(averages), 2)
        self.assertEqual(own_query_count(queries), 3)

    def test_level__rounds_to_the_nearest_level_halves_up(self):
        """ The average becomes a point on the scale by rounding, halves up; below a half it is no level """
        cases = [((2, 3), 3), ((3, 3, 2, 2, 0, 0), 2), ((4, 0), 2), ((1, 0, 0), 0), ((1, 0), 1), ((4, 4, 3), 4)]
        for levels, expected in cases:
            with self.subTest(levels=levels):
                competencies = [Competency(pk=pk) for pk in range(1, len(levels) + 1)]
                course = CourseCompetencies("ADST 9", competencies=competencies, levels=dict(zip(range(1, len(levels) + 1), levels)))
                self.assertEqual(course.level, expected)


class EvidenceByCompetencyTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for competencies.summaries.evidence_by_competency. """

    def test_evidence_by_competency__oldest_first_with_what_each_was_given_for(self):
        """ Each competency's evidence comes oldest first; a submission is described by its quest and links
        to the submission, even once the quest is archived and unpublished """
        brainstorm = self.submission("Brainstorm", archived=True, published=False)
        prototype = self.submission("Prototype")
        later = self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5, source=prototype)
        earlier = self.assess(self.defining, ProficiencyLevel.DEVELOPING, minutes_ago=60, source=brainstorm)

        evidence = evidence_by_competency(self.student)[self.defining.pk]

        self.assertEqual([item.assessment for item in evidence], [earlier, later])
        self.assertEqual([(item.description, item.url) for item in evidence], [
            ("Brainstorm", brainstorm.get_absolute_url()),
            ("Prototype", prototype.get_absolute_url()),
        ])

    def test_evidence_by_competency__sources_that_are_gone_or_not_submissions(self):
        """ A deleted quest says so; evidence with no source has no link; any other source is described by
        itself and links to its own page when it has one """
        gone = self.submission("Gone Quest")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=50, source=gone)
        gone.quest.delete()
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=40)
        other_quest = baker.make(Quest, name="A Quest Itself")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=30, source=other_quest)
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=20, source=self.making)

        evidence = evidence_by_competency(self.student)[self.defining.pk]

        self.assertEqual([(item.description, item.url) for item in evidence], [
            ("A deleted quest", None),
            ("No linked evidence", None),
            ("A Quest Itself", other_quest.get_absolute_url()),
            ("Use materials safely", None),
        ])

    def test_evidence_by_competency__queries_dont_grow_with_the_evidence(self):
        """ The submissions and their quests come with the rest, not one by one """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=self.submission("Q1"))
        with CaptureQueriesContext(connection) as one:
            evidence_by_competency(self.student)

        for minutes_ago, name in ((4, "Q2"), (3, "Q3"), (2, "Q4")):
            self.assess(self.making, ProficiencyLevel.EXTENDING, minutes_ago=minutes_ago, source=self.submission(name))
        with CaptureQueriesContext(connection) as four:
            names = [item.description for items in evidence_by_competency(self.student).values() for item in items]

        self.assertEqual(sorted(names), ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(own_query_count(four), own_query_count(one))


class ProfileCompetenciesTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for the Competencies panel and button on a student's profile. """

    def test_profile__a_row_per_course_with_its_average(self):
        """ Each course shows its average out of 4 and as the deck's label in the level's colour, with the
        student's course title, linked to the course on the competencies summary """
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.making, ProficiencyLevel.PROFICIENT, minutes_ago=10)
        self.assess(self.collaborating, ProficiencyLevel.EXTENDING, minutes_ago=10)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, '<h3 class="panel-title">Competencies</h3>')
        self.assertRegex(response.content.decode(), (
            rf'(?s)<a href="{self.summary_url()}#course-adst-9" class="list-group-item competency-level-row"\s*'
            r'title="The average current level across this course\'s 3 competencies, counting any not assessed yet as 0">\s*'
            r'<span class="competency-level-row-name">ADST 9 <small class="text-muted">\(Digital Hackerspace\)</small></span>\s*'
            r'<span class="competency-level-row-level">\s*<small class="text-muted">2.3 / 4</small>\s*'
            r'<span class="label competency-level competency-level-2">Developing</span>'
            rf'.*<a href="{self.summary_url()}#course-core".*?Core</span>.*?4.0 / 4</small>\s*'
            r'<span class="label competency-level competency-level-4">Nailed It</span>'
        ))

    def test_profile__a_course_below_the_scale_is_not_yet(self):
        """ A course averaging under half a level shows its average and "Not yet", in grey """
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, '<small class="text-muted">0.0 / 4</small>')
        self.assertContains(response, '<span class="label label-default">Not yet</span>', html=True)

    def test_profile__competencies_without_a_course_label(self):
        """ Competencies with no course label are grouped as "Other competencies" """
        self.assess(baker.make(Competency, course="", name="Homemade"), ProficiencyLevel.PROFICIENT, minutes_ago=5)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, f'href="{self.summary_url()}#course-other"')
        self.assertContains(response, '<span class="competency-level-row-name">Other competencies</span>', html=True)

    def test_profile__empty_state(self):
        """ A student in no course with a competency set, and with no evidence, gets the panel saying so """
        CourseStudent.objects.all().delete()
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, '<div class="list-group-item">None yet.</div>', html=True)

    def test_profile__summary_button_beside_mark_calculations(self):
        """ The profile's buttons include one to the student's competencies summary, after Mark Calculations """
        config = SiteConfig.get()
        config.display_marks_calculation = True
        config.save()
        self.client.force_login(self.teacher)

        response = self.client.get(self.profile_url())

        self.assertRegex(response.content.decode(), (
            rf'(?s)title="View your Mark Calculations".*?</a>\s*<a class="btn btn-default" title="View the Competencies Summary"\s*'
            rf'href="{self.summary_url()}"'
        ))

    def test_profile__levels_take_the_same_queries_however_many_competencies(self):
        """ The panel adds no query per competency or course """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        self.client.force_login(self.teacher)
        self.client.get(self.profile_url())  # warm up per-request caches, such as the deck's SiteConfig

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.profile_url())

        for competency in (self.making, self.collaborating, baker.make(Competency, course="Media Design 10")):
            self.assess(competency, ProficiencyLevel.DEVELOPING, minutes_ago=1)
        with CaptureQueriesContext(connection) as more:
            response = self.client.get(self.profile_url())

        self.assertEqual(response.content.decode().count('class="list-group-item competency-level-row"'), 3)
        self.assertEqual(own_query_count(more), own_query_count(one))

    def test_profile__nothing_when_disabled(self):
        """ With the flag off the profile has neither the panel nor the summary button """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        set_competencies_flag(False)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<h3 class="panel-title">Competencies</h3>')
        self.assertNotContains(response, self.summary_url())

    def test_profile__nothing_on_a_staff_profile(self):
        """ Teachers aren't assessed, so their own profile has neither the panel nor the summary button """
        self.client.force_login(self.teacher)

        response = self.client.get(self.profile_url(self.teacher))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<h3 class="panel-title">Competencies</h3>')
        self.assertNotContains(response, self.summary_url(self.teacher))


class CompetencySummaryViewTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencySummaryView, a student's competencies summary. """

    def test_summary__each_course_with_a_chip_per_assessment(self):
        """ Each course shows its average, then its competencies by category, each with a chip per
        assessment, oldest first, in the deck's labels and colours, linking to the submission and titled
        with the quest and date; a competency not assessed yet says so """
        brainstorm = self.submission("Brainstorm")
        prototype = self.submission("Prototype")
        self.assess(self.defining, ProficiencyLevel.DEVELOPING, minutes_ago=60 * 24 * 3, source=brainstorm)
        latest = self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5, source=prototype)
        self.assess(self.collaborating, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=prototype)
        self.client.force_login(self.teacher)

        response = self.client.get(self.summary_url())

        self.assertContains(response, '<i class="fa fa-graduation-cap pull-right"></i>Grace&#x27;s Competencies</h1>')
        self.assertContains(response, f'For <a href="{self.student.profile.get_absolute_url()}">Grace Hopper</a>')
        content = response.content.decode()
        self.assertRegex(content, (
            r'(?s)<div class="panel panel-primary" id="course-adst-9">.*?ADST 9 <small>\(Digital Hackerspace\)</small>.*?1.3 / 4\s*'
            r'<span class="label competency-level competency-level-1">Emerging</span>'
            r'.*?<tr class="info"><th colspan="2">Applied Design - Defining</th></tr>\s*<tr>\s*'
            r'<td title="ADST 9: Applied Design - Defining: Choose a design opportunity">Choose a design opportunity</td>\s*'
            r'<td class="competency-summary-evidence">\s*'
            rf'<a href="{brainstorm.get_absolute_url()}" class="label competency-level competency-level-2"\s*'
            r'title="Brainstorm, [^"]+">Developing</a>\s*'
            rf'<a href="{prototype.get_absolute_url()}" class="label competency-level competency-level-4"\s*'
            r'title="Prototype, [^"]+">Nailed It</a>'
            r'.*?Generate potential ideas</td>\s*<td class="competency-summary-evidence">\s*<span class="text-muted">Not yet</span>'
            r'.*?<div class="panel panel-primary" id="course-core">.*?competency-level-3"\s*title="Prototype, [^"]+">Got It</a>'
        ))
        self.assertIn(f'title="Prototype, {latest.timestamp:%b}', content)
        self.assertNotContains(response, "Retired competency")

    def test_summary__the_student_sees_their_own_with_links(self):
        """ A student sees their own summary, with each chip linking to their submission """
        submission = self.submission("Brainstorm")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=submission)
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertContains(response, f'<a href="{submission.get_absolute_url()}" class="label competency-level competency-level-3"')

    def test_summary__evidence_without_a_link_is_a_plain_chip(self):
        """ A chip whose work is gone, or that has none, isn't a link, and its title says why """
        gone = self.submission("Gone Quest")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=10, source=gone)
        gone.quest.delete()
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.client.force_login(self.teacher)

        content = self.client.get(self.summary_url()).content.decode()

        self.assertRegex(content, r'<span class="label competency-level competency-level-3"\s*title="A deleted quest, [^"]+">Got It</span>')
        self.assertRegex(content, r'<span class="label competency-level competency-level-4"\s*title="No linked evidence, [^"]+">Nailed It</span>')

    def test_summary__empty_state(self):
        """ A student in no course with a competency set, and with no evidence, is told so """
        CourseStudent.objects.all().delete()
        self.client.force_login(self.student)

        self.assertContains(self.client.get(self.summary_url()), "None yet: a course's competencies show here")

    def test_summary__queries_dont_grow_with_the_evidence(self):
        """ The page's queries stay the same however many assessments there are """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=self.submission("Q1"))
        self.client.force_login(self.teacher)
        self.client.get(self.summary_url())  # warm up per-request caches

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.summary_url())

        for minutes_ago, name in ((4, "Q2"), (3, "Q3"), (2, "Q4")):
            self.assess(self.making, ProficiencyLevel.EXTENDING, minutes_ago=minutes_ago, source=self.submission(name))
        with CaptureQueriesContext(connection) as four:
            response = self.client.get(self.summary_url())

        self.assertContains(response, ">Nailed It</a>", count=3)
        self.assertEqual(own_query_count(four), own_query_count(one))

    def test_summary__another_students_is_not_found(self):
        """ A student can't see another student's summary: the page doesn't exist for them """
        other_student = User.objects.create_user('other_student')
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(self.summary_url(other_student)).status_code, 404)

    def test_summary__anonymous_users_are_sent_to_log_in(self):
        """ The page needs a logged-in user """
        response = self.client.get(self.summary_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_summary__unknown_student_is_not_found(self):
        """ A URL naming a user that doesn't exist is a 404 """
        self.client.force_login(self.teacher)

        self.assertEqual(self.client.get(reverse('competencies:summary', args=[0])).status_code, 404)

    def test_summary__not_found_when_disabled(self):
        """ With the flag off the page doesn't exist, even for staff """
        set_competencies_flag(False)
        self.client.force_login(self.teacher)

        self.assertEqual(self.client.get(self.summary_url()).status_code, 404)
