from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from courses.models import Block, Course, CourseStudent, Semester, Rank, ExcludedDate
from hackerspace_online.tests.utils import ViewTestUtilsMixin, generate_form_data, model_to_form_data, generate_formset_data
from siteconfig.models import SiteConfig
from courses.forms import SemesterForm, ExcludedDateFormset, CourseStudentStaffForm

import random
import datetime
import itertools
import json

User = get_user_model()


class RankViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

    def test_all_rank_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to login page '''

        self.assertRedirectsLogin('courses:ranks')
        self.assertRedirectsLogin('courses:rank_create')
        self.assertRedirectsLogin('courses:rank_update', args=[1])
        self.assertRedirectsLogin('courses:rank_delete', args=[1])

    def test_all_rank_page_status_codes_for_students(self):
        ''' If logged in as student then all views except ranks list view should redirect to login page '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:ranks')

        # staff access only
        self.assert403('courses:rank_create')
        self.assert403('courses:rank_update', args=[1])
        self.assert403('courses:rank_delete', args=[1])

    def test_all_rank_page_status_codes_for_staff(self):
        ''' If logged in as staff then all views should return code 200 for successful retrieval of page '''
        self.client.force_login(self.test_teacher)

        self.assert200('courses:ranks')
        self.assert200('courses:rank_create')
        self.assert200('courses:rank_update', args=[1])
        self.assert200('courses:rank_delete', args=[1])

    def test_RanksList_view(self):
        """ Admin and students should be able to view ranks. Anonymous users should be asked to login if they attempt to view ranks. """

        # Anonymous user
        self.assertRedirectsLogin('courses:ranks')

        # student
        self.client.force_login(self.test_student1)
        response = self.client.get(reverse('courses:ranks'))
        self.assertEqual(response.status_code, 200)

        # teacher
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:ranks'))
        self.assertEqual(response.status_code, 200)

        # Should contain 13 default ranks e.g. Digital Novice, Digital Ameteur II, etc
        self.assertEqual(response.context['object_list'].count(), 13)

    def test_RankCreate_view(self):
        """ Admin should be able to create a rank """
        self.client.force_login(self.test_teacher)
        data = {
            'name': 'My Sample rank',
            'xp': 23,
            'fa_icon': 'fa fa-circle-o'
        }
        response = self.client.post(reverse('courses:rank_create'), data=data)
        self.assertRedirects(response, reverse('courses:ranks'))

        rank = Rank.objects.get(name=data['name'])
        self.assertEqual(rank.name, data['name'])

    def test_RankUpdate_view(self):
        """ Admin should be able to update a rank """
        self.client.force_login(self.test_teacher)
        data = {
            'name': 'My updated rank',
            'xp': 23,
            'fa_icon': 'fa fa-circle-o'
        }
        response = self.client.post(reverse('courses:rank_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('courses:ranks'))
        rank = Rank.objects.get(id=1)
        self.assertEqual(rank.name, data['name'])
        self.assertEqual(rank.xp, data['xp'])

    def test_RankDelete_view(self):
        """ Admin should be able to delete a rank """
        self.client.force_login(self.test_teacher)

        before_delete_count = Rank.objects.count()
        response = self.client.post(reverse('courses:rank_delete', args=[1]))
        after_delete_count = Rank.objects.count()
        self.assertRedirects(response, reverse('courses:ranks'))
        self.assertEqual(before_delete_count - 1, after_delete_count)


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
        }

    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page '''
        self.assertRedirectsLogin('courses:create')
        self.assertRedirectsLogin('courses:join', args=[1])
        self.assertRedirectsLogin('courses:coursestudent_delete', args=[1])
        self.assertRedirectsLogin('courses:ranks')
        self.assertRedirectsLogin('courses:my_marks')
        self.assertRedirectsLogin('courses:marks', args=[1])
        self.assertRedirectsLogin('courses:end_active_semester')
        self.assertRedirectsLogin('courses:ajax_progress_chart', args=[1])

        self.assertRedirectsLogin('courses:semester_list')
        self.assertRedirectsLogin('courses:semester_create')
        self.assertRedirectsLogin('courses:semester_update', args=[1])

        self.assertRedirectsLogin('courses:block_list')
        self.assertRedirectsLogin('courses:block_create')
        self.assertRedirectsLogin('courses:block_update', args=[1])
        self.assertRedirectsLogin('courses:block_delete', args=[1])

        self.assertRedirectsLogin('courses:course_list')
        self.assertRedirectsLogin('courses:course_create')
        self.assertRedirectsLogin('courses:course_update', args=[1])
        self.assertRedirectsLogin('courses:course_delete', args=[1])
        # View from external package.  Need to override view with LoginRequiredMixin if we want to bother
        # self.assertRedirectsLogin('courses:mark_distribution_chart', args=[1])

        # Refer to rank specific tests for Rank CRUD views

    def test_all_page_status_codes_for_students(self):
        ''' Test student access to views '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:create')
        self.assert200('courses:ranks')

        # 404 unless SiteConfig has marks turned on
        self.assert404('courses:my_marks')
        self.assert404('courses:marks', args=[self.test_student1.id])

        # 404 unless ajax POST request
        self.assert404('courses:ajax_progress_chart', args=[self.test_student1.id])

        # Staff access only
        self.assert403('courses:join', args=[self.test_student1.id])
        self.assert403('courses:end_active_semester')
        self.assert403('courses:coursestudent_delete', args=[1])

        self.assert403('courses:semester_list')
        self.assert403('courses:semester_create')
        self.assert403('courses:semester_update', args=[1])

        self.assert403('courses:block_list')
        self.assert403('courses:block_create')
        self.assert403('courses:block_update', args=[1])
        self.assert403('courses:block_delete', args=[1])

        self.assert403('courses:course_list')
        self.assert403('courses:course_create')
        self.assert403('courses:course_update', args=[1])
        self.assert403('courses:course_delete', args=[1])

        # Refer to rank specific tests for Rank CRUD views

    def test_all_page_status_codes_for_staff(self):
        self.client.force_login(self.test_teacher)

        # Staff access only
        self.assert200('courses:join', args=[self.test_student1.id])

        # Redirects, has own test
        # self.assert200('courses:end_active_semester')

        self.assert200('courses:semester_list')
        self.assert200('courses:semester_create')
        self.assert200('courses:semester_update', args=[1])

        self.assert200('courses:block_list')
        self.assert200('courses:block_create')
        self.assert200('courses:block_update', args=[1])
        self.assert200('courses:block_delete', args=[1])

        self.assert200('courses:course_list')
        self.assert200('courses:course_create')
        self.assert200('courses:course_update', args=[1])
        self.assert200('courses:course_delete', args=[1])

    def test_course_student_update_status_codes(self):
        course_student = baker.make(CourseStudent)
        # anon
        self.client.logout()
        self.assertRedirectsLogin('courses:update', args=[course_student.id])

        # stud
        self.client.force_login(self.test_student1)
        self.assert403('courses:update', args=[course_student.id])
        self.client.logout()

        # staff
        self.client.force_login(self.test_teacher)
        self.assert200('courses:update', args=[course_student.id])
        self.client.logout()

    def test_end_active_semester__staff(self):
        ''' End_active_semester view should redirect to semester list view '''
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        self.assertFalse(active_sem.closed)
        self.assertRedirects(
            response=self.client.get(reverse('courses:end_active_semester')),
            expected_url=reverse('courses:semester_list'),
        )
        active_sem.refresh_from_db()
        self.assertTrue(active_sem.closed)

    def test_SemesterActivate(self):
        """When this view is accessed, the siteconfig's active semester should be changed
        and the view should redirect tot he semester_list """
        self.client.force_login(self.test_teacher)
        new_semester = baker.make('courses.semester')
        response = self.client.get(reverse('courses:semester_activate', args=[new_semester.pk]))
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(SiteConfig.get().active_semester, Semester.objects.get(pk=new_semester.pk))

    def test_CourseStudentUpdate_view(self):
        """ Staff can update a student's course """

        course_student = baker.make(
            CourseStudent,
            user=self.test_student1,
            course=self.course,
            block=self.block,
            semester=SiteConfig.get().active_semester
        )
        new_course = baker.make(Course)

        form_data = model_to_form_data(course_student, CourseStudentStaffForm)
        form_data['course'] = new_course.pk

        self.client.force_login(self.test_teacher)
        response = self.client.post(reverse('courses:update', args=[course_student.pk]), data=form_data)
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[course_student.user.profile.pk]))

        course_student.refresh_from_db()
        self.assertEqual(course_student.course.pk, new_course.pk)

    def test_CourseAddStudent_view(self):
        '''Staff can add a student to a course'''

        # Almost similar to `test_CourseStudentCreate_view` but just uses courses:join
        # and redirects to profiles:profile_detail

        self.client.force_login(self.test_teacher)
        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        add_course_url = reverse('courses:join', args=[self.test_student1.id])

        response = self.client.get(add_course_url)
        self.assertContains(response, f'Adding a course for {self.test_student1}')

        response = self.client.post(add_course_url, data=self.valid_form_data)
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.id]))
        # Student should now be registered in a course
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Now try adding them a second time, should not validate:
        response = self.client.post(add_course_url, data=self.valid_form_data)

        # invalid form
        # GRADE field is depercated and no longer used within unique_together
        # form = response.context['form']
        # self.assertFalse(form.is_valid())
        # self.assertEqual(response.status_code, 200)
        # self.assertContains(response, 'Student Course with this User, Course and Grade already exists')
        # self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the grade, still fails cus same block in same semester
        self.valid_form_data['grade_fk'] = baker.make('courses.grade').pk
        response = self.client.post(add_course_url, data=self.valid_form_data)
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this Semester, Group and User already exists')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the block also, should validate now
        self.valid_form_data['block'] = baker.make('courses.block').pk
        response = self.client.post(add_course_url, data=self.valid_form_data)
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.id]))
        self.assertEqual(self.test_student1.coursestudent_set.count(), 2)

    def test_CourseStudentDelete_view(self):
        """ Teacher should be able to delete a student from a course (StudentCourse object)
        and should redirect to the student's profile when complete. """
        self.client.force_login(self.test_teacher)
        course_student = baker.make(CourseStudent, user=self.test_student1)

        # can access the Delete View
        response = self.client.get(reverse('courses:coursestudent_delete', args=[course_student.id]))
        self.assertEqual(response.status_code, 200)

        before_delete_count = CourseStudent.objects.count()
        response = self.client.post(reverse('courses:coursestudent_delete', args=[course_student.id]))
        after_delete_count = CourseStudent.objects.count()
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.profile.id]))
        self.assertEqual(before_delete_count - 1, after_delete_count)

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

    def test_CourseDelete_view__no_students(self):
        """ Admin should be able to delete a course """
        self.client.force_login(self.test_teacher)

        before_delete_count = Course.objects.count()
        response = self.client.post(reverse('courses:course_delete', args=[1]))
        after_delete_count = Course.objects.count()
        self.assertRedirects(response, reverse('courses:course_list'))
        self.assertEqual(before_delete_count - 1, after_delete_count)

    def test_CourseDelete_view__with_students(self):
        """
            Admin should not be able to delete course with a student registered
            Also checks if course can be deleted with a forced post method
        """
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # register student to course
        course_student = baker.make(CourseStudent, user=self.test_student1, semester=self.sem, block=self.block, course=self.course,)
        self.assertEqual(CourseStudent.objects.count(), 1)
        self.assertEqual(CourseStudent.objects.first().pk, course_student.pk)

        # confirm course existence
        self.assertTrue(Course.objects.exists())

        # confirm deletion prevention text shows up
        response = self.client.get(reverse('courses:course_delete', args=[self.course.pk]))

        dt_ptag = f"Unable to delete '{self.course.title}' as it still has students registered. Consider disabling the course by toggling the"
        dt_atag_link = reverse("courses:course_update", args=[self.course.pk])
        dt_well_ptag = f"Registered Students: {self.course.coursestudent_set.count()}"
        self.assertContains(response, dt_ptag)
        self.assertContains(response, dt_atag_link)
        self.assertContains(response, dt_well_ptag)


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

        # GRADE has been deprecated and is no longer part of a unique requirement
        # invalid form
        # form = response.context['form']
        # self.assertFalse(form.is_valid())
        # self.assertEqual(response.status_code, 200)
        # self.assertContains(response, 'Student Course with this User, Course and Grade already exists')
        # self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Change the grade, still fails cus same block in same semester
        self.valid_form_data['grade_fk'] = baker.make('courses.grade').pk
        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Course with this Semester, Group and User already exists')
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

    def generate_dates(quantity, dates=None):
        """
            Small recursive function that gets n unique dates
        """
        if dates is None:
            dates = []

        if max(quantity, 0) == 0:
            return dates

        dates += [datetime.date(
            random.randint(2000, 2020),  # year
            random.randint(1, 12),  # month
            random.randint(1, 28),  # day
        ) for i in range(quantity)]
        dates = list(set(dates))  # make it so unique only

        leftover = quantity - len(dates)
        return SemesterViewTests.generate_dates(leftover, dates)

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password='password', is_staff=True)

    def test_SemesterList_view(self):
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('courses:semester_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['object_list'].count(), 1)

        for obj in response.context['object_list']:
            self.assertContains(response, obj.num_days())
            self.assertContains(response, obj.excludeddate_set.count())

    def test_SemesterCreate__without_ExcludedDates__view(self):
        self.client.force_login(self.test_teacher)

        post_data = {
            'first_day': '2020-10-15', 'last_day': '2020-12-15',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }
        response = self.client.post(reverse('courses:semester_create'), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.count(), 2)

    def test_SemesterCreate__with_ExcludedDates__view(self):
        """
            Test for SemesterCreate with correct/valid post data.
            valid post data includes default values for SemesterForm, randomly generated values for ExcludedDateFormset
        """
        self.client.force_login(self.test_teacher)

        # need to generate dates here sinces its unique only (generate_formset_data cant handle validators)
        exclude_dates = SemesterViewTests.generate_dates(5)

        post_data = {
            **generate_form_data(model_form=SemesterForm),
            **generate_formset_data(ExcludedDateFormset, quantity=len(exclude_dates), date=itertools.cycle(exclude_dates)),
        }
        response = self.client.post(reverse('courses:semester_create'), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))

        # check if data was added to db
        self.assertEqual(Semester.objects.count(), 2)
        semester = Semester.objects.get(pk=2)

        self.assertTrue(semester.excludeddate_set.exists())
        for ed in semester.excludeddate_set.all():
            self.assertTrue(ed.date in exclude_dates)

    def test_SemesterCreate__add_without_required_fields__view(self):
        """
            Test for SemesterCreate with leaving required fields blank
        """
        self.client.force_login(self.test_teacher)

        form_data = generate_form_data(model_form=SemesterForm)
        formset_data = generate_formset_data(ExcludedDateFormset, quantity=5, label="filler text", date=None)

        # test with response
        response = self.client.post(reverse('courses:semester_create'), data={**form_data, **formset_data})
        self.assertEqual(response.status_code, 200)

        self.assertFalse(response.context['formset'].is_valid())

    def test_SemesterUpdate_view(self):
        self.client.force_login(self.test_teacher)

        post_data = {
            'first_day': '2020-10-16',
            'last_day': '2020-12-16',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }
        response = self.client.post(reverse('courses:semester_update', args=[1]), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.get(id=1).first_day.strftime('%Y-%m-%d'), post_data['first_day'])

    def test_SemesterUpdate__add_data__view(self):
        """
             Test for SemesterUpdate with correct/valid post data.
             Only add data for ExcludeDateFormset related fields
        """
        self.client.force_login(self.test_teacher)

        # need to generate dates here sinces its unique only (generate_formset_data cant handle validators)
        exclude_dates = SemesterViewTests.generate_dates(5)

        semester = SiteConfig.get().active_semester

        post_data = {
            **model_to_form_data(semester, SemesterForm),
            **generate_formset_data(ExcludedDateFormset, quantity=len(exclude_dates), date=itertools.cycle(exclude_dates)),
        }
        response = self.client.post(reverse('courses:semester_update', args=[semester.pk]), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))

        self.assertTrue(semester.excludeddate_set.exists())
        for ed in semester.excludeddate_set.all():
            self.assertTrue(ed.date in exclude_dates)

    def test_SemesterUpdate__update_data__view(self):
        """
             Test for SemesterUpdate with correct/valid post data.
             Only update/add data for ExcludeDateFormset related fields
        """
        self.client.force_login(self.test_teacher)
        semester = SiteConfig.get().active_semester
        dates = SemesterViewTests.generate_dates(13)

        old_exclude_dates = dates[:5]
        updated_exclude_dates = dates[:2] + dates[5:]

        # load data to semester before updating it
        excludeddates_set = baker.make(ExcludedDate, semester=semester, date=itertools.cycle(old_exclude_dates), _quantity=len(old_exclude_dates))

        form_data = model_to_form_data(semester, SemesterForm)
        formset_data = generate_formset_data(ExcludedDateFormset, quantity=len(updated_exclude_dates), date=itertools.cycle(updated_exclude_dates))

        # update management form
        formset_data.update({
            'form-INITIAL_FORMS': len(old_exclude_dates)
        })
        # give existing dates an id
        for index in range(len(old_exclude_dates)):
            formset_data[f'form-{index}-id'] = excludeddates_set[index].id

        response = self.client.post(reverse('courses:semester_update', args=[semester.pk]), data={**form_data, **formset_data})
        self.assertRedirects(response, reverse('courses:semester_list'))

        # assert data is correct
        for ed in semester.excludeddate_set.all():
            self.assertTrue(ed.date in updated_exclude_dates)

    def test_SemesterUpdate__delete_data__view(self):
        """
             Test for SemesterUpdate with correct/valid post data.
             Only delete data for ExcludeDateFormset related fields
        """
        self.client.force_login(self.test_teacher)
        semester = SiteConfig.get().active_semester

        dates = SemesterViewTests.generate_dates(10)
        excludeddates_set = baker.make(ExcludedDate, semester=semester, date=itertools.cycle(dates), _quantity=len(dates))

        form_data = model_to_form_data(semester, SemesterForm)
        formset_data = generate_formset_data(ExcludedDateFormset, quantity=len(dates), date=itertools.cycle(dates))

        # update management form
        formset_data.update({
            'form-INITIAL_FORMS': len(dates)
        })

        # give existing dates an id + delete=on
        for index in range(len(dates)):
            formset_data[f'form-{index}-id'] = excludeddates_set[index].id
            formset_data[f'form-{index}-DELETE'] = 'on'

        response = self.client.post(reverse('courses:semester_update', args=[semester.pk]), data={**form_data, **formset_data})
        self.assertRedirects(response, reverse('courses:semester_list'))

        self.assertFalse(ExcludedDate.objects.exists())

    @patch('profile_manager.models.Profile.xp_per_course')
    def test_SemesterDCloses__student_with_negative_xp__view(self, xp_per_course):
        """
            Test if SemesterClose returns a warning when there is a course student with
            a negative xp.
        """
        xp_per_course.return_value = -10
        self.client.force_login(self.test_teacher)

        post_data = {
            'first_day': '2020-10-15', 'last_day': '2020-12-15',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }
        response = self.client.post(reverse('courses:semester_create'), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.count(), 2)

        semester = Semester.objects.first()
        student = baker.make(User)
        course = baker.make(Course)
        baker.make(CourseStudent, user=student, course=course, semester=semester)

        response = self.client.post(reverse('courses:end_active_semester'))
        self.assertWarningMessage(response)
        self.assertRedirects(response, reverse('courses:semester_list'))
        message = self.get_message_list(response)[0]
        self.assertIn('There are some students with negative XP', str(message))


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
            'name': 'My Block',
        }

        response = self.client.post(reverse('courses:block_create'), data=data)
        self.assertRedirects(response, reverse('courses:block_list'))

        block = Block.objects.get(name=data['name'])
        self.assertEqual(block.name, data['name'])

    def test_BlockUpdate_view(self):
        """ Admin should be able to update a block """
        self.client.force_login(self.test_teacher)
        data = {
            'name': 'Updated Block',
        }
        response = self.client.post(reverse('courses:block_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('courses:block_list'))
        block = Block.objects.get(id=1)
        self.assertEqual(block.name, data['name'])

    def test_BlockDelete_view__no_students(self):
        """ Admin should be able to delete a block """
        self.client.force_login(self.test_teacher)

        before_delete_count = Block.objects.count()
        response = self.client.post(reverse('courses:block_delete', args=[1]))
        after_delete_count = Block.objects.count()
        self.assertRedirects(response, reverse('courses:block_list'))
        self.assertEqual(before_delete_count - 1, after_delete_count)

    def test_BlockDelete_view__with_students(self):
        """
            Admin should not be able to delete block with a student registered
            Also checks if block can be deleted with a forced post method
        """
        student = baker.make(User)
        block = baker.make(Block)

        success = self.client.login(username=self.test_teacher.username, password='password')
        self.assertTrue(success)

        # register student to block
        course_student = baker.make(CourseStudent, user=student, block=block)
        self.assertEqual(CourseStudent.objects.count(), 1)
        self.assertEqual(CourseStudent.objects.first().pk, course_student.pk)

        # confirm block existence
        self.assertTrue(Block.objects.filter(id=block.pk).first() is not None)

        # confirm deletion prevention text shows up
        response = self.client.get(reverse('courses:block_delete', args=[block.pk]))

        dt_ptag = f"Unable to delete '{block.name}' as it still has students registered. Consider disabling the block by toggling the"
        dt_atag_link = reverse('courses:block_update', args=[block.pk])
        dt_well_ptag = f"Registered Students: {block.coursestudent_set.count()}"
        self.assertContains(response, dt_ptag)
        self.assertContains(response, dt_atag_link)
        self.assertContains(response, dt_well_ptag)

    def test_BlockForm_initial_values(self):
        """
            Test if the form passed through context has correct initial values
        """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:block_create'))
        form = response.context['form']

        self.assertEqual(form['current_teacher'].value(), SiteConfig.get().deck_owner.pk)


class TestAjax_MarkDistributionChart(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.teacher = baker.make(User, is_staff=True)

        self.block = baker.make(Block)
        self.course = baker.make(Course)
        self.semester = SiteConfig.get().active_semester
        self.inactive_semester = baker.make(Semester)

    def create_student_course(self, xp):
        """
        Quick helper function to create student course

        Args:
            xp (int): how much xp will be stored in new_user.profile.xp_cached

        Returns:
            CourseStudent: instance of course student that uses self.block, self.course, self.semester as its variables
        """
        user = baker.make(User)

        user.profile.xp_cached = xp
        user.profile.save()

        return baker.make(CourseStudent, user=user, semester=self.semester, course=self.course, block=self.block)

    def test_non_ajax_status_code(self):
        self.assert404('courses:mark_distribution_chart', args=[self.teacher.pk])

    def test_ajax_status_code_for_anonymous(self):
        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 404)

    def test_ajax_status_code_for_students(self):
        user = baker.make(User)
        self.client.force_login(user)

        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    def test_ajax_status_code_for_teachers(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    def test_no_users_outside_active_semester_in_histogram_values(self):
        """ histogram values should only belong to users who belong in the active semester"""
        # create inactive semester students
        inactive_sem_students = [self.create_student_course(100) for i in range(5)]
        for cs in inactive_sem_students:
            cs.semester = (self.inactive_semester)
            cs.save()

        # create active semester students
        active_sem_students = [self.create_student_course(100) for i in range(7)]

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('courses:mark_distribution_chart', args=[active_sem_students[0].user.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        json_response = json.loads(response.content)

        # total students in hist should be total + user
        total_students = sum(json_response['data']['students'])
        self.assertNotEqual(total_students, len(inactive_sem_students))
        self.assertEqual(total_students, len(active_sem_students))

    def test_no_test_users_in_histogram_values(self):
        """ test users should not show up in histogram values """
        # create test users students
        test_account_students = [self.create_student_course(100) for i in range(5)]
        for cs in test_account_students:
            cs.user.profile.is_test_account = True
            cs.user.profile.save()

        # create active semester students
        active_sem_students = [self.create_student_course(100) for i in range(7)]

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('courses:mark_distribution_chart', args=[active_sem_students[0].user.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        json_response = json.loads(response.content)

        # total students in hist should be total + users
        total_students = sum(json_response['data']['students'])
        self.assertNotEqual(total_students, len(test_account_students))
        self.assertEqual(total_students, len(active_sem_students))
