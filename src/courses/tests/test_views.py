from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from model_bakery import baker
from siteconfig.models import SiteConfig
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

User = get_user_model()


class CourseViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

        self.sem = SiteConfig.get().active_semester
        self.block = baker.make('courses.block')
        self.course = baker.make('courses.course')
        self.grade = baker.make('courses.grade')

        self.valid_form_data = {
            'semester': self.sem.pk,
            'block': self.block.pk,
            'course': self.course.pk,
            'grade_fk': self.grade.pk
        }

    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.assertRedirectsLogin('courses:create')
        self.assertRedirectsAdmin('courses:add', args=[1])
        self.assertRedirectsLogin('courses:ranks')
        self.assertRedirectsLogin('courses:my_marks')
        self.assertRedirectsLogin('courses:marks', args=[1])
        self.assertRedirectsAdmin('courses:end_active_semester')
        self.assertRedirectsLogin('courses:ajax_progress_chart', args=[1])
        # View from external package.  Need to override view with LoginRequiredMixin if we want to bother
        # self.assertRedirectsLogin('courses:mark_distribution_chart', args=[1])

    def test_all_page_status_codes_for_students(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:create')
        self.assert200('courses:ranks')

        # ?
        # self.assert200('courses:mark_distribution_chart', args=[self.test_student1.id])

        # 404 unless SiteConfig has marks turned on
        self.assert404('courses:my_marks')
        self.assert404('courses:marks', args=[self.test_student1.id])
        # 404 unless ajax POST request
        self.assert404('courses:ajax_progress_chart', args=[self.test_student1.id])

        # Staff access only
        self.assertRedirectsAdmin('courses:add', args=[self.test_student1.id])
        self.assertRedirectsAdmin('courses:end_active_semester')

    def test_all_page_status_codes_for_staff(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.client.force_login(self.test_teacher)

        # Staff access only
        self.assert200('courses:add', args=[self.test_student1.id])

        self.assertRedirects(
            response=self.client.get(reverse('courses:end_active_semester')),
            expected_url=reverse('config:site_config_update_own'),
        )

    def test_CourseAddStudent_view(self):
        '''Admin can add a student to a course'''

        # Almost similar to `test_CourseStudentCreate_view` but just uses courses:add
        # and redirects to profiles:profile_detail

        self.client.force_login(self.test_teacher)
        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        add_course_url = reverse('courses:add', args=[self.test_student1.id])

        response = self.client.get(add_course_url)
        self.assertContains(response, 'Adding a course for {student}'.format(student=self.test_student1))

        response = self.client.post(add_course_url, data=self.valid_form_data)
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.id]))
        # Student should now be registered in a course
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Now try adding them a second time, should not validate:
        response = self.client.post(add_course_url, data=self.valid_form_data)

        # invalid form
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this User, Course and Grade already exists')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the grade, still fails cus same block in same semester
        self.valid_form_data['grade_fk'] = baker.make('courses.grade').pk
        response = self.client.post(add_course_url, data=self.valid_form_data)
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this Semester, Block and User already exists')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the block also, should validate now
        self.valid_form_data['block'] = baker.make('courses.block').pk
        response = self.client.post(add_course_url, data=self.valid_form_data)
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.id]))
        self.assertEqual(self.test_student1.coursestudent_set.count(), 2)


class CourseStudentViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

        self.sem = SiteConfig.get().active_semester
        self.block = baker.make('courses.block')
        self.course = baker.make('courses.course')
        self.grade = baker.make('courses.grade')

        self.valid_form_data = {
            'semester': self.sem.pk,
            'block': self.block.pk,
            'course': self.course.pk,
            'grade_fk': self.grade.pk
        }

    def test_CourseStudentCreate_view(self):
        '''Student can register themself in a course'''
        self.client.force_login(self.test_student1)

        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)

        self.assertRedirects(response, reverse('quests:quests'))
        # Student should now be registered in a course
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Now try adding them a second time, should not validate:
        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)

        # invalid form
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this User, Course and Grade already exists')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the grade, still fails cus same block in same semester
        self.valid_form_data['grade_fk'] = baker.make('courses.grade').pk
        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this Semester, Block and User already exists')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the block also, should validate now
        self.valid_form_data['block'] = baker.make('courses.block').pk
        # print(self.valid_form_data)
        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)
        # form = response.context['form']
        # print(form)
        # self.assertFalse(form.is_valid())
        self.assertRedirects(response, reverse('quests:quests'))
        self.assertEqual(self.test_student1.coursestudent_set.count(), 2)
