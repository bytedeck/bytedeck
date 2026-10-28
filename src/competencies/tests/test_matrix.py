import csv
import io

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel
from competencies.summaries import course_competencies, course_matrix
from competencies.tests.test_approval import set_competencies_flag
from competencies.tests.test_profile_views import own_query_count
from competencies.views import csv_safe
from courses.models import Block, Course, CourseStudent, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class CompetencyMatrixMixin:
    """ A course, "Digital Hackerspace", whose competency set is ADST 9 (two active competencies and two
    deactivated ones), with two students in it this semester in blocks A and B, on a deck with
    competencies enabled; plus a teacher, and a Core competency outside the set. """

    def setUp(self):
        """ Creates the course, blocks, students, registrations and competencies. """
        set_competencies_flag(True, competency_label_level_3="Got It")
        self.teacher = User.objects.create_user('matrix_teacher', is_staff=True)
        self.semester = SiteConfig.get().active_semester
        self.semester.status = Semester.Status.OPEN
        self.semester.save()
        self.course = baker.make(Course, title="Digital Hackerspace", competency_set="ADST 9")
        self.block_a = baker.make(Block, name="A")
        self.block_b = baker.make(Block, name="B")
        self.zed = User.objects.create_user('zed', first_name="Zoe", last_name="Zed")
        self.adams = User.objects.create_user('adams', first_name="Ann", last_name="Adams")
        self.zed_registration = self.register(self.zed, self.block_a)
        self.adams_registration = self.register(self.adams, self.block_b)

        self.defining = baker.make(Competency, course="ADST 9", category="Defining", name="Choose a design opportunity")
        self.making = baker.make(Competency, course="ADST 9", category="Making", name="Use materials safely")
        self.retired = baker.make(Competency, course="ADST 9", category="Making", name="Retired with evidence", active=False)
        self.unused = baker.make(Competency, course="ADST 9", category="Making", name="Retired without evidence", active=False)
        self.core = baker.make(Competency, course="Core", category="Communication", name="Collaborating")

    def register(self, user, block, course=None, semester=None):
        """ Registers a user in a course (this class's by default) and block, in a semester (the open one by default).

        Returns:
            CourseStudent: the registration.
        """
        return baker.make(CourseStudent, user=user, course=course or self.course, semester=semester or self.semester, block=block)

    def assess(self, user, competency, level):
        """ Records an assessment of a user.

        Returns:
            CompetencyAssessment: the saved assessment.
        """
        return CompetencyAssessment.objects.create(user=user, competency=competency, level=level)

    def matrix_url(self, **params):
        """ The matrix's URL, with any query parameters. """
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return reverse('competencies:matrix') + (f"?{query}" if query else "")


class CourseMatrixTest(CompetencyMatrixMixin, ByteDeckTenantTestCase):
    """ Tests for competencies.summaries.course_matrix. """

    def test_course_matrix__the_course_students_by_last_name(self):
        """ The rows are the course's students this semester, by last name: not staff, test accounts or
        inactive users, nor registrations in an archived semester or in another course """
        self.register(baker.make(User, is_staff=True), self.block_a)
        tester = User.objects.create_user('tester')
        tester.profile.is_test_account = True
        tester.profile.save()
        self.register(tester, self.block_a)
        self.register(baker.make(User, is_active=False), self.block_a)
        archived = baker.make(Semester, status=Semester.Status.ARCHIVED)
        self.register(baker.make(User), self.block_a, semester=archived)
        self.register(baker.make(User), self.block_a, course=baker.make(Course, competency_set="ADST 9"))

        columns, rows = course_matrix(self.course)

        self.assertEqual([row.registration for row in rows], [self.adams_registration, self.zed_registration])

    def test_course_matrix__one_block(self):
        """ Given a block, only its students are rows """
        columns, rows = course_matrix(self.course, self.block_a)

        self.assertEqual([row.registration for row in rows], [self.zed_registration])

    def test_course_matrix__columns_and_levels(self):
        """ The columns are the set's active competencies plus deactivated ones some row has evidence for;
        each row has the student's current levels, counts a deactivated competency only when that student
        has evidence for it, and matches the student's own competencies page for the course """
        self.assess(self.zed, self.defining, ProficiencyLevel.DEVELOPING)
        self.assess(self.zed, self.defining, ProficiencyLevel.EXTENDING)
        self.assess(self.zed, self.retired, ProficiencyLevel.PROFICIENT)
        self.assess(self.zed, self.core, ProficiencyLevel.EMERGING)
        self.assess(self.adams, self.making, ProficiencyLevel.PROFICIENT)

        columns, rows = course_matrix(self.course)

        self.assertEqual(columns, [self.defining, self.retired, self.making])
        adams, zed = rows
        self.assertEqual(zed.levels, {self.defining.pk: ProficiencyLevel.EXTENDING, self.retired.pk: ProficiencyLevel.PROFICIENT})
        self.assertEqual(zed.competencies, [self.defining, self.retired, self.making])
        self.assertEqual(adams.competencies, [self.defining, self.making])
        for row in rows:
            with self.subTest(student=row.registration.user.username):
                own = next(course for course in course_competencies(row.registration.user) if course.registration == row.registration)
                self.assertEqual((row.competencies, row.average, row.level), (own.competencies, own.average, own.level))

    def test_course_matrix__three_queries(self):
        """ It takes three queries however many students and competencies there are """
        for _ in range(5):
            student = baker.make(User)
            self.register(student, self.block_a)
            for competency in (self.defining, self.making, self.retired):
                self.assess(student, competency, ProficiencyLevel.PROFICIENT)

        with CaptureQueriesContext(connection) as queries:
            columns, rows = course_matrix(self.course)
            names = [(row.registration.user.profile.teacher_name(), row.registration.block.name, row.average) for row in rows]

        self.assertEqual(len(names), 7)
        self.assertEqual(own_query_count(queries), 3)


class CompetencyMatrixViewTest(CompetencyMatrixMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencyMatrixView, the staff competency matrix and its CSV. """

    def test_matrix__a_row_per_student_and_a_column_per_competency(self):
        """ Each student has their current level of proficiency, linked to their competencies page, then a
        fixed-width code per competency, linked to that competency on their page, or "n/a"; the columns
        stand under their categories, and a key gives the Proficiency Scale """
        self.assess(self.zed, self.defining, ProficiencyLevel.PROFICIENT)
        self.assess(self.zed, self.making, ProficiencyLevel.EXTENDING)
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url())

        content = response.content.decode()
        self.assertContains(response, '<i class="fa fa-graduation-cap pull-right"></i>Competency Matrix</h1>')
        self.assertContains(response, "<strong>Digital Hackerspace</strong> (ADST 9):")
        self.assertRegex(content, (
            r'(?s)Proficiency Scale:\s*<span class="label competency-code competency-level competency-level-1">EMG</span> Emerging'
            r'.*?competency-level-3">GOT</span> Got It.*?<span class="label competency-code label-default">n/a</span> Not yet assessed'
        ))
        self.assertRegex(content, (
            r'(?s)<th colspan="1" class="competency-matrix-category">Defining</th><th colspan="1" class="competency-matrix-category">Making</th>'
            r'.*?<th class="competency-matrix-name" title="ADST 9: Defining: Choose a design opportunity"><div>Choose a design opportunity</div></th>'
        ))
        summary = reverse('competencies:summary', args=[self.zed.pk])
        pane = f"course-pane-{self.zed_registration.pk}"
        self.assertRegex(content, (
            rf'(?s)<td><a href="{self.zed.profile.get_absolute_url()}">Zoe Zed</a></td>\s*<td>A</td>\s*<td>\s*'
            rf'<a href="{summary}\?course={pane}"\s*title="3.50 / 4"><span class="label competency-level competency-level-4">Extending</span></a>'
            rf'.*?<a href="{summary}\?course={pane}#{pane}-competency-{self.defining.pk}"\s*'
            r'class="label competency-code competency-level competency-level-3" title="Got It: Choose a design opportunity">GOT</a>'
            rf'.*?<a href="{summary}\?course={pane}#{pane}-competency-{self.making.pk}"\s*'
            r'class="label competency-code competency-level competency-level-4" title="Extending: Use materials safely">EXT</a>'
        ))
        self.assertRegex(content, r'(?s)Ann Adams</a></td>\s*<td>B</td>.*?<span class="text-muted" title="Not yet assessed">n/a</span>')
        self.assertNotContains(response, "Retired without evidence")

    def test_matrix__a_cell_opens_its_competency_on_the_students_page(self):
        """ The student's competencies page has the row a cell links to """
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('competencies:summary', args=[self.zed.pk]), {'course': f"course-pane-{self.zed_registration.pk}"})

        self.assertContains(response, f'<tr id="course-pane-{self.zed_registration.pk}-competency-{self.defining.pk}">')

    def test_matrix__choosing_the_course(self):
        """ The courses offered are the active ones with a competency set; the first is shown unless another
        is chosen, and an unknown choice shows the first """
        baker.make(Course, title="Inactive Course", competency_set="ADST 9", active=False)
        baker.make(Course, title="No Set")
        other = baker.make(Course, title="Computer Programming 11", competency_set="Computer Programming 11")
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url())

        self.assertEqual(response.context['courses'], [other, self.course])
        self.assertEqual(response.context['course'], other)
        self.assertContains(response, f'<a href="?course={other.pk}" role="button" class="btn btn-primary">Computer Programming 11</a>', html=True)
        self.assertNotContains(response, "Inactive Course")
        self.assertNotContains(response, "No Set")
        self.assertContains(response, "No students are in Computer Programming 11 this semester.")

        self.assertEqual(self.client.get(self.matrix_url(course=self.course.pk)).context['course'], self.course)
        self.assertEqual(self.client.get(self.matrix_url(course="nonsense")).context['course'], other)

    def test_matrix__choosing_the_block(self):
        """ The blocks offered are those with students in the course; choosing one shows only its students,
        and an unknown choice shows them all """
        baker.make(Block, name="Empty Block")
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url(course=self.course.pk, block=self.block_b.pk))

        self.assertEqual(response.context['blocks'], [self.block_a, self.block_b])
        self.assertEqual(response.context['selected_block'], self.block_b)
        self.assertEqual([row['course'].registration for row in response.context['rows']], [self.adams_registration])
        self.assertContains(
            response, f'<a href="?course={self.course.pk}&amp;block={self.block_b.pk}" role="button" class="btn btn-primary">B</a>', html=True,
        )
        self.assertContains(response, f'href="?course={self.course.pk}&amp;block={self.block_b.pk}&amp;format=csv"')
        self.assertNotContains(response, "Empty Block")

        response = self.client.get(self.matrix_url(course=self.course.pk, block="nonsense"))

        self.assertIsNone(response.context['selected_block'])
        self.assertEqual(len(response.context['rows']), 2)
        self.assertContains(response, f'href="?course={self.course.pk}&amp;format=csv"')

    def test_matrix__no_course_with_a_set(self):
        """ With no course that has a competency set, the page says how to give one a set (and the CSV
        link has nothing to download, so it shows the page) """
        Course.objects.update(competency_set='')
        self.client.force_login(self.teacher)

        for params in ({}, {'format': 'csv'}):
            with self.subTest(**params):
                response = self.client.get(self.matrix_url(**params))

                self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
                self.assertContains(response, "No course has a competency set yet.")
                self.assertNotContains(response, "competency-matrix-filters")

    def test_matrix__csv(self):
        """ The CSV has a row per student with their name, username, block, average and current level of
        proficiency, then each competency (headed by category and name) by the deck's labels, or n/a """
        config = SiteConfig.get()
        config.custom_name_for_group = "Class"
        config.save()
        self.assess(self.zed, self.defining, ProficiencyLevel.PROFICIENT)
        self.assess(self.zed, self.making, ProficiencyLevel.EXTENDING)
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url(course=self.course.pk, block=self.block_a.pk, format='csv'))

        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="digital-hackerspace-a-competencies.csv"')
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode()))), [
            [
                'Student', 'Username', 'Class', 'Average', 'Current level of proficiency',
                'Defining: Choose a design opportunity', 'Making: Use materials safely',
            ],
            ['Zoe Zed', 'zed', 'A', '3.50', 'Extending', 'Got It', 'Extending'],
        ])

        response = self.client.get(self.matrix_url(course=self.course.pk, format='csv'))

        self.assertEqual(response['Content-Disposition'], 'attachment; filename="digital-hackerspace-competencies.csv"')
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode())))[1], ['Ann Adams', 'adams', 'B', '0.00', 'n/a', 'n/a', 'n/a'])

    def test_matrix__csv_text_never_runs_as_a_formula(self):
        """ Text that a spreadsheet would run as a formula (a student's own name, a username, a group, an
        imported competency) is written with a leading quote, so opening the CSV runs nothing """
        self.zed.first_name = '=HYPERLINK("http://example.com","Zoe")'
        self.zed.save()
        self.zed.username = '+zed'
        self.zed.save()
        self.block_a.name = '@A'
        self.block_a.save()
        self.defining.category = ''
        self.defining.name = '-1+2'
        self.defining.save()
        self.making.name = '\tTabbed'
        self.making.save()
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url(course=self.course.pk, block=self.block_a.pk, format='csv'))

        header, zed = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(header[5:], ["'-1+2", 'Making: \tTabbed'])
        self.assertEqual(zed[:4], ['\'=HYPERLINK("http://example.com","Zoe") Zed', "'+zed", "'@A", '0.00'])

    def test_csv_safe__quotes_only_formula_starts(self):
        """ Only text starting as a spreadsheet formula does gets the quote; None is empty """
        cases = [
            ('=1+1', "'=1+1"), ('+1', "'+1"), ('-1', "'-1"), ('@SUM(A1)', "'@SUM(A1)"), ('\tx', "'\tx"), ('\rx', "'\rx"),
            ('Zoe Zed', 'Zoe Zed'), ('1.50', '1.50'), ('a=b', 'a=b'), ('', ''), (None, ''),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(csv_safe(value), expected)

    def test_matrix__queries_dont_grow_with_the_class(self):
        """ The page takes the same queries however many students and assessments there are """
        self.assess(self.zed, self.defining, ProficiencyLevel.PROFICIENT)
        self.client.force_login(self.teacher)
        self.client.get(self.matrix_url())  # warm up per-request caches

        with CaptureQueriesContext(connection) as small:
            self.client.get(self.matrix_url())

        for _ in range(4):
            student = baker.make(User)
            self.register(student, self.block_b)
            for competency in (self.defining, self.making):
                self.assess(student, competency, ProficiencyLevel.DEVELOPING)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.matrix_url())

        self.assertEqual(len(response.context['rows']), 6)
        self.assertEqual(own_query_count(large), own_query_count(small))

    def test_matrix__staff_only(self):
        """ Students get the 403 page, and anonymous users are sent to log in """
        self.client.force_login(self.zed)
        self.assertEqual(self.client.get(self.matrix_url()).status_code, 403)

        self.client.logout()
        response = self.client.get(self.matrix_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_matrix__not_found_when_disabled(self):
        """ With the flag off the page doesn't exist, even for staff """
        set_competencies_flag(False)
        self.client.force_login(self.teacher)

        self.assertEqual(self.client.get(self.matrix_url()).status_code, 404)

    def test_matrix__linked_from_the_competencies_list_and_course_list(self):
        """ The Competencies list has a Matrix button, and the course list links each active course's set
        to its matrix (an inactive course's set is shown without a link) """
        inactive = baker.make(Course, title="Old Course", competency_set="Media Design 10", active=False)
        self.client.force_login(self.teacher)

        self.assertContains(self.client.get(reverse('competencies:list')), f'href="{self.matrix_url()}"')

        response = self.client.get(reverse('courses:course_list'))

        link = f'<a href="{self.matrix_url(course=self.course.pk)}" title="See this course\'s students by competency">ADST 9</a>'
        self.assertContains(response, link)
        self.assertNotContains(response, self.matrix_url(course=inactive.pk))
        self.assertContains(response, "<td>Media Design 10</td>")
