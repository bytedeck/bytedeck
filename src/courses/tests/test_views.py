from django.contrib.auth import get_user_model
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from courses.models import Block, Course, Semester
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

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

        self.assertRedirectsAdmin('courses:semester_list')
        self.assertRedirectsAdmin('courses:semester_create')
        self.assertRedirectsAdmin('courses:semester_update', args=[1])

        self.assertRedirectsAdmin('courses:block_list')
        self.assertRedirectsAdmin('courses:block_create')
        self.assertRedirectsAdmin('courses:block_update', args=[1])
        self.assertRedirectsAdmin('courses:block_delete', args=[1])

        self.assertRedirectsAdmin('courses:course_list')
        self.assertRedirectsAdmin('courses:course_create')
        self.assertRedirectsAdmin('courses:course_update', args=[1])
        self.assertRedirectsAdmin('courses:course_delete', args=[1])
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

        self.assertRedirectsAdmin('courses:semester_list')
        self.assertRedirectsAdmin('courses:semester_create')
        self.assertRedirectsAdmin('courses:semester_update', args=[1])

        self.assertRedirectsAdmin('courses:block_list')
        self.assertRedirectsAdmin('courses:block_create')
        self.assertRedirectsAdmin('courses:block_update', args=[1])
        self.assertRedirectsAdmin('courses:block_delete', args=[1])

        self.assertRedirectsAdmin('courses:course_list')
        self.assertRedirectsAdmin('courses:course_create')
        self.assertRedirectsAdmin('courses:course_update', args=[1])
        self.assertRedirectsAdmin('courses:course_delete', args=[1])

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

    def test_CourseList_view(self):
        """ Admin should be able to view course list """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:course_list'))
        self.assertEqual(response.status_code, 200)

        # Should contain Default and another one via bake
        self.assertEqual(response.context['object_list'].count(), 2)

    def test_CourseCreate_view(self):
        """ Admin should be able to create a course """
        self.client.force_login(self.test_teacher)
        data = {
            'title': 'My Sample Course',
            'xp_for_100_percent': 2000
        }
        response = self.client.post(reverse('courses:course_create'), data=data)
        self.assertRedirects(response, reverse('courses:course_list'))

        course = Course.objects.get(title=data['title'])
        self.assertEqual(course.title, data['title'])

    def test_CourseUpdate_view(self):
        """ Admin should be able to update a course """
        self.client.force_login(self.test_teacher)
        data = {
            'title': 'My Updated Title',
            'xp_for_100_percent': 1000,
        }
        response = self.client.post(reverse('courses:course_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('courses:course_list'))
        course = Course.objects.get(id=1)
        self.assertEqual(course.title, data['title'])
        self.assertEqual(course.xp_for_100_percent, data['xp_for_100_percent'])

    def test_CourseDelete_view(self):
        """ Admin should be able to delete a course """
        self.client.force_login(self.test_teacher)

        before_delete_count = Course.objects.count()
        response = self.client.post(reverse('courses:course_delete', args=[1]))
        after_delete_count = Course.objects.count()
        self.assertRedirects(response, reverse('courses:course_list'))
        self.assertEqual(before_delete_count - 1, after_delete_count)


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


class SemesterViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password='password', is_staff=True)

    def test_SemesterList_view(self):
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('courses:semester_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['object_list'].count(), 1)

    def test_SemesterCreate_view(self):
        self.client.force_login(self.test_teacher)

        response = self.client.post(reverse('courses:semester_create'), data={'first_day': '2020-10-15', 'last_day': '2020-12-15'})
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.count(), 2)

    def test_SemesterUpdate_view(self):
        self.client.force_login(self.test_teacher)

        first_day = '2020-10-16'
        response = self.client.post(reverse('courses:semester_update', args=[1]), data={'first_day': first_day})
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.get(id=1).first_day.strftime('%Y-%m-%d'), first_day)


class BlockViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password='password', is_staff=True)

    def test_BlockList_view(self):
        """ Admin should be able to view block list """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:block_list'))
        self.assertEqual(response.status_code, 200)

        # Should contain one block
        self.assertEqual(response.context['object_list'].count(), 1)

    def test_BlockCreate_view(self):
        """ Admin should be able to create a block """
        self.client.force_login(self.test_teacher)
        data = {
            'block': 'My Block',
        }

        response = self.client.post(reverse('courses:block_create'), data=data)
        self.assertRedirects(response, reverse('courses:block_list'))

        block = Block.objects.get(block=data['block'])
        self.assertEqual(block.block, data['block'])

    def test_BlockUpdate_view(self):
        """ Admin should be able to update a block """
        self.client.force_login(self.test_teacher)
        data = {
            'block': 'Updated Block',
        }
        response = self.client.post(reverse('courses:block_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('courses:block_list'))
        block = Block.objects.get(id=1)
        self.assertEqual(block.block, data['block'])

    def test_BlockDelete_view(self):
        """ Admin should be able to delete a block """
        self.client.force_login(self.test_teacher)

        before_delete_count = Block.objects.count()
        response = self.client.post(reverse('courses:block_delete', args=[1]))
        after_delete_count = Block.objects.count()
        self.assertRedirects(response, reverse('courses:block_list'))
        self.assertEqual(before_delete_count - 1, after_delete_count)
