from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.template.defaultfilters import date as date_filter
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel
from competencies.summaries import CourseCompetencies, course_competencies, evidence_by_competency, level_codes
from competencies.tests.test_approval import set_competencies_flag
from courses.models import Block, Course, CourseStudent, Semester
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
    """ A teacher, and a student registered this semester in "Digital Hackerspace" (block A), whose
    competency set is ADST 9 (three active competencies and a deactivated one), on a deck with
    competencies enabled, which also has a Core competency. """

    def setUp(self):
        """ Creates the users, the course and registration, and the competencies. """
        set_competencies_flag(True, competency_label_level_3="Got It", competency_label_level_4="Nailed It")
        self.teacher = User.objects.create_user('summary_teacher', first_name="Ada", last_name="Lovelace", is_staff=True)
        self.student = User.objects.create_user('summary_student', first_name="Grace", last_name="Hopper")
        self.semester = SiteConfig.get().active_semester
        self.semester.status = Semester.Status.OPEN
        self.semester.save()
        self.course = baker.make(Course, title="Digital Hackerspace", competency_set="ADST 9")
        self.registration = baker.make(
            CourseStudent, user=self.student, course=self.course, semester=self.semester, block=baker.make(Block, name="A"),
        )

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
        """ The student's course averages the current level of each of its set's active competencies, with
        0 for one not assessed yet: Extending (the latest of two), nothing, and Proficient make 7/3 """
        self.assess(self.defining, ProficiencyLevel.DEVELOPING, minutes_ago=30)
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.making, ProficiencyLevel.PROFICIENT, minutes_ago=10)

        [adst] = course_competencies(self.student)

        self.assertEqual((adst.label, adst.registration, adst.title), ("ADST 9", self.registration, "Digital Hackerspace"))
        self.assertEqual(adst.pane_id, f"course-pane-{self.registration.pk}")
        self.assertEqual(adst.competencies, [self.defining, self.ideating, self.making])
        self.assertCountEqual(adst.course_levels, [ProficiencyLevel.EXTENDING, ProficiencyLevel.PROFICIENT])
        self.assertEqual(adst.total, 7)
        self.assertAlmostEqual(adst.average, 7 / 3)
        self.assertEqual(adst.level, ProficiencyLevel.DEVELOPING)

    def test_course_competencies__a_registered_course_shows_before_any_evidence(self):
        """ A course the student is in shows from the start, at an average of 0 and no level """
        [adst] = course_competencies(self.student)

        self.assertEqual(adst.average, 0)
        self.assertEqual(adst.level, 0)

    def test_course_competencies__the_students_courses_come_first_then_other_sets_with_evidence(self):
        """ After the student's courses come the other sets they have evidence in, by label, named by
        their label (or "Other competencies" for none) """
        self.assess(self.collaborating, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(baker.make(Competency, course="ADST 8", name="Older"), ProficiencyLevel.PROFICIENT, minutes_ago=5)
        self.assess(baker.make(Competency, course="", name="Homemade"), ProficiencyLevel.PROFICIENT, minutes_ago=5)

        courses = course_competencies(self.student)

        self.assertEqual([(course.title, course.registration) for course in courses], [
            ("Digital Hackerspace", self.registration), ("Other competencies", None), ("ADST 8", None), ("Core", None),
        ])
        self.assertEqual([course.pane_id for course in courses[1:]], ["course-pane-other", "course-pane-adst-8", "course-pane-core"])
        self.assertEqual(courses[3].average, ProficiencyLevel.EXTENDING)

    def test_course_competencies__a_set_with_no_competencies_is_left_out(self):
        """ A course whose set has no competencies on the deck has nothing to show, so it is left out """
        self.course.competency_set = "Vanished Set"
        self.course.save()

        self.assertEqual(course_competencies(self.student), [])

    def test_course_competencies__a_deactivated_competency_counts_once_assessed(self):
        """ A deactivated competency is left out of its course, unless the student already has evidence for it """
        self.assess(self.retired, ProficiencyLevel.PROFICIENT, minutes_ago=5)

        [adst] = course_competencies(self.student)

        self.assertIn(self.retired, adst.competencies)
        self.assertEqual(adst.average, 3 / 4)

    def test_course_competencies__two_courses_with_the_same_set_each_show(self):
        """ Each of the student's courses with a set shows, even two that chose the same set """
        other = baker.make(CourseStudent, user=self.student, course=baker.make(Course, title="ADST 9 Honours", competency_set="ADST 9"),
                           semester=self.semester)

        registrations = [course.registration for course in course_competencies(self.student)]

        self.assertCountEqual(registrations, [self.registration, other])

    def test_course_competencies__a_course_without_a_set_adds_nothing(self):
        """ A course the student is in that hasn't chosen a competency set adds no course """
        baker.make(CourseStudent, user=self.student, course=baker.make(Course, title="Study Hall"), semester=self.semester)

        self.assertEqual([course.title for course in course_competencies(self.student)], ["Digital Hackerspace"])

    def test_course_competencies__three_queries(self):
        """ It takes three queries however many courses and competencies there are """
        for competency in (self.defining, self.making, self.collaborating):
            self.assess(competency, ProficiencyLevel.PROFICIENT, minutes_ago=5)

        with CaptureQueriesContext(connection) as queries:
            courses = course_competencies(self.student)
            summaries = [(course.title, course.average) for course in courses]

        self.assertEqual(len(summaries), 2)
        self.assertEqual(own_query_count(queries), 3)

    def test_average__a_course_with_no_competencies_is_zero(self):
        """ A course with no competencies averages 0, rather than dividing by zero """
        self.assertEqual(CourseCompetencies("Empty").average, 0)
        self.assertEqual(CourseCompetencies("Empty").level, 0)

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


class LevelCodesTest(ByteDeckTenantTestCase):
    """ Tests for competencies.summaries.level_codes. """

    def test_level_codes__default_labels_use_the_default_codes(self):
        """ A deck using the default labels gets EMG, DEV, PRF and EXT """
        self.assertEqual(level_codes({1: "Emerging", 2: "Developing", 3: "Proficient", 4: "Extending"}), {1: "EMG", 2: "DEV", 3: "PRF", 4: "EXT"})

    def test_level_codes__a_renamed_level_uses_its_own_label(self):
        """ A level the deck has renamed gets the first three letters or digits of its label, uppercased;
        a label with none keeps the default code """
        self.assertEqual(
            level_codes({1: "Emerging", 2: "Not quite!", 3: "Got It", 4: "\u2605\u2605"}),
            {1: "EMG", 2: "NOT", 3: "GOT", 4: "EXT"},
        )


class ProfileCompetenciesTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for the current levels of proficiency in the XP panel of a student's profile, and its
    summary button. """

    def test_profile__each_course_shows_its_current_level_of_proficiency(self):
        """ Beside each course's name in the XP panel is "Current level of proficiency:" and the course's
        level as the deck's label in its colour (with no number out of 4), linking to the course on the
        competencies page; a course without a set has none, and sets outside the student's courses aren't
        shown here """
        baker.make(CourseStudent, user=self.student, course=baker.make(Course, title="Study Hall"), semester=self.semester)
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.making, ProficiencyLevel.PROFICIENT, minutes_ago=10)
        self.assess(self.collaborating, ProficiencyLevel.EXTENDING, minutes_ago=10)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        content = response.content.decode()
        self.assertRegex(content, (
            r'(?s)<div>\s*Digital Hackerspace\s*<span class="course-competency-average">\s*'
            r'<small class="text-muted">Current level of proficiency:</small>\s*'
            rf'<a href="{self.summary_url()}\?course=course-pane-{self.registration.pk}"\s*'
            r'class="label competency-level competency-level-2"\s*'
            r'title="See how your current level of proficiency in Digital Hackerspace is worked out">Developing</a>\s*</span>\s*</div>'
        ))
        self.assertRegex(content, r'<div>\s*Study Hall\s*</div>')
        self.assertEqual(content.count('class="course-competency-average"'), 1)
        self.assertNotContains(response, ' / 4')

    def test_profile__a_course_below_the_scale_is_n_a(self):
        """ A course averaging under half a level shows "n/a", for not yet assessed, in grey """
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertRegex(response.content.decode(), r'class="label label-default"\s*title="Not yet assessed. See how [^"]+">n/a</a>')

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
        """ The levels add no query per competency assessed (course_competencies takes the same three
        queries however many courses there are, as its own test shows) """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        self.client.force_login(self.teacher)
        self.client.get(self.profile_url())  # warm up per-request caches, such as the deck's SiteConfig

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.profile_url())

        for competency in (self.making, self.ideating, self.collaborating):
            self.assess(competency, ProficiencyLevel.DEVELOPING, minutes_ago=1)
        with CaptureQueriesContext(connection) as more:
            response = self.client.get(self.profile_url())

        self.assertContains(response, 'class="label competency-level competency-level-2"')
        self.assertEqual(own_query_count(more), own_query_count(one))

    def test_profile__nothing_when_disabled(self):
        """ With the flag off the profile has neither the levels nor the summary button """
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        set_competencies_flag(False)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'course-competency-average')
        self.assertNotContains(response, self.summary_url())

    def test_profile__no_button_on_a_staff_profile(self):
        """ Teachers aren't assessed, so their own profile has no summary button """
        self.client.force_login(self.teacher)

        response = self.client.get(self.profile_url(self.teacher))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.summary_url(self.teacher))


class CompetencySummaryViewTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencySummaryView, a student's competencies summary. """

    def test_summary__a_table_of_courses_then_a_tab_each_listing_every_competency(self):
        """ Like Mark Calculations: a table of the student's courses (then other sets with evidence) with
        each one's average and current level of proficiency, then a tab per course listing all its
        competencies by category, each with its current level's three-letter code (or "n/a") then a
        fixed-width chip per assessment showing its code, oldest first, linking to the submission and titled
        with the level, quest and date, or "n/a" """
        brainstorm = self.submission("Brainstorm")
        prototype = self.submission("Prototype")
        self.assess(self.defining, ProficiencyLevel.DEVELOPING, minutes_ago=60 * 24 * 3, source=brainstorm)
        latest = self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5, source=prototype)
        self.assess(self.collaborating, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=prototype)
        self.client.force_login(self.teacher)

        response = self.client.get(self.summary_url())

        self.assertContains(response, '<i class="fa fa-graduation-cap pull-right"></i>Competencies for Grace Hopper</h1>')
        self.assertContains(response, "Hello Grace,")
        content = response.content.decode()
        pane = f"course-pane-{self.registration.pk}"
        self.assertRegex(content, (
            r'(?s)<th>Block</th>\s*<th>Course</th>\s*<th>Average</th>\s*<th>Current level of proficiency</th>'
            r'.*?<td>A</td>\s*<td>Digital Hackerspace <small class="text-muted">\(ADST 9\)</small></td>\s*<td>1.33 / 4</td>\s*'
            r'<td><span class="label competency-level competency-level-1">Emerging</span>\s*</td>'
            r'.*?<td></td>\s*<td>Core</td>\s*<td>3.00 / 4</td>\s*<td><span class="label competency-level competency-level-3">Got It</span>'
            rf'.*?<ul class="nav nav-tabs course-tabs" role="tablist">.*?<li role="presentation" class="active">\s*'
            rf'<a href="#{pane}" role="tab" data-toggle="tab">Digital Hackerspace</a>'
            r'.*?<a href="#course-pane-core" role="tab" data-toggle="tab">Core</a>'
            rf'.*?<div role="tabpanel" class="tab-pane active" id="{pane}">\s*<h3>Explanation</h3>.*?<h3>ADST 9 Competencies</h3>'
            r'.*?<th class="competency-summary-name">Competency</th>\s*<th>Current level</th>\s*<th>Assessments, oldest first</th>'
            r'.*?<tr class="info"><th colspan="3">Applied Design - Defining</th></tr>\s*'
            rf'<tr id="{pane}-competency-{self.defining.pk}">\s*'
            r'<td title="ADST 9: Applied Design - Defining: Choose a design opportunity">Choose a design opportunity</td>\s*'
            r'<td class="competency-summary-current">\s*'
            r'<span class="label competency-code competency-level competency-level-4" title="Nailed It">NAI</span>\s*</td>\s*'
            r'<td class="competency-summary-evidence">\s*'
            rf'<a href="{brainstorm.get_absolute_url()}" class="label competency-code competency-level competency-level-2"\s*'
            r'title="Developing: Brainstorm, [^"]+">DEV</a>\s*'
            rf'<a href="{prototype.get_absolute_url()}" class="label competency-code competency-level competency-level-4"\s*'
            r'title="Nailed It: Prototype, [^"]+">NAI</a>'
            r'.*?Generate potential ideas</td>\s*<td class="competency-summary-current">\s*'
            r'<span class="text-muted" title="Not yet assessed">n/a</span>\s*</td>\s*<td class="competency-summary-evidence">\s*'
            r'<span class="text-muted" title="Not yet assessed">n/a</span>'
            r'.*?<div role="tabpanel" class="tab-pane " id="course-pane-core">\s*<h3>Explanation</h3>.*?<h3>Core Competencies</h3>'
            r'.*?competency-level-3"\s*title="Got It: Prototype, [^"]+">GOT</a>'
        ))
        # the chip's date as the template's date filter renders it: the stored (backdated) stamp, in the deck's time zone
        latest.refresh_from_db()
        self.assertIn(f'title="Nailed It: Prototype, {date_filter(timezone.localtime(latest.timestamp))}"', content)
        self.assertNotContains(response, "Retired competency")

    def test_summary__each_course_explains_how_its_level_is_worked_out(self):
        """ At the top of each course's tab: how many competencies it has and what each point on the
        Proficiency Scale counts, the student's levels in it and their total, the average out of 4, and the
        current level of proficiency it rounds to, with the averages that round to each point on the scale
        (by code and label) and the student's highlighted """
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.making, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.ideating, ProficiencyLevel.DEVELOPING, minutes_ago=5)
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        content = response.content.decode()
        self.assertContains(response, "Here is how your current level of proficiency in <strong>Digital Hackerspace</strong> is worked out:")
        self.assertRegex(content, (
            r'(?s)ADST 9 has <strong>3</strong> competencies\. Each counts at your\s*current level in it, '
            r'which is the level of its most recent assessment, '
            r'on the Proficiency Scale:\s*Emerging \(EMG\) counts 1, Developing \(DEV\) counts 2, '
            r'Got It \(GOT\) counts 3, Nailed It \(NAI\) counts 4\.\s*'
            r'A competency not yet assessed \(n/a\) counts 0\.'
            r'.*?You have been assessed in <strong>3</strong> of them\s*\(1 Developing, 2 Nailed It\),\s*which add up to <strong>10</strong>\.'
            r'.*?Your average is 10 / 3 = <strong>3.33</strong> out of 4\.'
            r'.*?rounded to the nearest point on the Proficiency Scale, with halves rounding up, so your\s*'
            r'current level of proficiency is: <span class="label competency-level competency-level-3">Got It</span>'
            r'.*?<th>Average out of 4</th>\s*<th>Proficiency Scale</th>'
            r'.*?<tr>\s*<td>1.5 to under 2.5</td>'
            r'.*?<tr class="info">\s*<td><strong>2.5 to under 3.5</strong></td>\s*<td>\s*'
            r'<span class="label competency-code competency-level competency-level-3">GOT</span> Got It'
            r'.*?<td>3.5 to 4</td>\s*<td>\s*<span class="label competency-code competency-level competency-level-4">NAI</span> Nailed It'
        ))

    def test_summary__explanation_before_any_assessment(self):
        """ A course with nothing assessed yet explains that everything adds up to 0, which is "n/a", not
        yet assessed """
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        content = response.content.decode()
        self.assertRegex(content, r"You haven't been assessed in any of them yet, so they add up to <strong>0</strong>\.")
        self.assertContains(response, "Your average is 0 / 3 = <strong>0.00</strong> out of 4.")
        self.assertRegex(content, r'current level of proficiency is: <span class="label label-default" title="Not yet assessed">n/a</span>')
        self.assertRegex(content, (
            r'<tr class="info">\s*<td><strong>under 0.5</strong></td>\s*<td>\s*'
            r'<span class="label competency-code label-default">n/a</span> Not yet assessed'
        ))

    def test_summary__the_course_in_the_url_opens_its_tab(self):
        """ A course named in the URL, as the profile links, has its tab open; an unknown one opens the first """
        self.assess(self.collaborating, ProficiencyLevel.PROFICIENT, minutes_ago=5)
        self.client.force_login(self.student)
        first = f"course-pane-{self.registration.pk}"

        response = self.client.get(self.summary_url(), {'course': 'course-pane-core'})

        self.assertContains(response, '<li role="presentation" class="active">\n      <a href="#course-pane-core"')
        self.assertContains(response, '<div role="tabpanel" class="tab-pane active" id="course-pane-core">')
        self.assertContains(response, f'<div role="tabpanel" class="tab-pane " id="{first}">')

        response = self.client.get(self.summary_url(), {'course': 'nonsense'})

        self.assertContains(response, f'<div role="tabpanel" class="tab-pane active" id="{first}">')

    def test_summary__one_course_has_no_tabs(self):
        """ A student with one course gets its competencies without a tab strip over them """
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertContains(response, f'<div role="tabpanel" class="tab-pane active" id="course-pane-{self.registration.pk}">')
        self.assertNotContains(response, 'nav-tabs')

    def test_summary__the_student_sees_their_own_with_links(self):
        """ A student sees their own summary, titled without their name, with each chip linking to their submission """
        submission = self.submission("Brainstorm")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=submission)
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertContains(response, '<i class="fa fa-graduation-cap pull-right"></i>Competencies</h1>')
        self.assertContains(response, f'<a href="{submission.get_absolute_url()}" class="label competency-code competency-level competency-level-3"')

    def test_summary__evidence_without_a_link_is_a_plain_chip(self):
        """ A chip whose work is gone, or that has none, isn't a link, and its title says why """
        gone = self.submission("Gone Quest")
        self.assess(self.defining, ProficiencyLevel.PROFICIENT, minutes_ago=10, source=gone)
        gone.quest.delete()
        self.assess(self.defining, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.client.force_login(self.teacher)

        content = self.client.get(self.summary_url()).content.decode()

        self.assertRegex(content, (
            r'<span class="label competency-code competency-level competency-level-3"\s*title="Got It: A deleted quest, [^"]+">GOT</span>'
        ))
        self.assertRegex(content, (
            r'<span class="label competency-code competency-level competency-level-4"\s*title="Nailed It: No linked evidence, [^"]+">NAI</span>'
        ))

    def test_summary__empty_state(self):
        """ A student in no course with a competency set, and with no evidence, is told so """
        CourseStudent.objects.all().delete()
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertContains(response, "there are no competencies to show yet")
        self.assertNotContains(response, "course-tab-content")

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

        self.assertContains(response, ">NAI</a>", count=3)
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
