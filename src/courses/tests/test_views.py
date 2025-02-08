from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.utils import timezone

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker
from freezegun import freeze_time

from courses.forms import CourseStudentStaffForm, ExcludedDateFormset, SemesterForm
from courses.models import Block, Course, CourseStudent, MarkRange, Semester, Rank, ExcludedDate
from notifications.models import Notification, notify_rank_up
from hackerspace_online.tests.utils import ViewTestUtilsMixin, generate_form_data, model_to_form_data, generate_formset_data
from siteconfig.models import SiteConfig
from djcytoscape.models import CytoScape

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

    def test_scape_update_message_on_update_delete(self):
        """ Checks if delete and update function gives a success message when a rank is related to map """
        # setup
        rank = baker.make(Rank, name='rank')
        scape = CytoScape.generate_map(rank, name='unique scape name')

        self.client.force_login(self.test_teacher)

        # test messages for quest_update
        response = self.client.post(reverse('courses:rank_update', args=[rank.id]), data={
            'name': 'rank', 'xp': 0, 'fa_icon': 'fa fa-circle-o'
        })
        messages = list(response.wsgi_request._messages)  # unittest dont carry messages when redirecting
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(messages), 1)
        self.assertTrue(scape.name in str(messages[0]))

        # to clear any messages before next test
        self.assert200('courses:ranks')

        # test messages for quest_delete
        response = self.client.post(reverse('courses:rank_delete', args=[rank.id]))
        messages = list(response.wsgi_request._messages)  # unittest dont carry messages when redirecting
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(messages), 1)
        self.assertTrue(scape.name in str(messages[0]))


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

        self.assertRedirectsLogin('courses:markranges')
        self.assertRedirectsLogin('courses:markrange_create')
        self.assertRedirectsLogin('courses:markrange_update', args=[1])
        self.assertRedirectsLogin('courses:markrange_delete', args=[1])

        self.assertRedirectsLogin('courses:semester_list')
        self.assertRedirectsLogin('courses:semester_create')
        self.assertRedirectsLogin('courses:semester_update', args=[1])
        self.assertRedirectsLogin('courses:semester_delete', args=[1])

        self.assertRedirectsLogin('courses:block_list')
        self.assertRedirectsLogin('courses:block_create')
        self.assertRedirectsLogin('courses:block_update', args=[1])
        self.assertRedirectsLogin('courses:block_delete', args=[1])

        self.assertRedirectsLogin('courses:course_list')
        self.assertRedirectsLogin('courses:course_create')
        self.assertRedirectsLogin('courses:course_update', args=[1])
        self.assertRedirectsLogin('courses:course_delete', args=[1])
        # View from external package.  Need to override view with LoginRequiredMixin if we want to bother

        # Refer to rank specific tests for Rank CRUD views

    def test_all_page_status_codes_for_students(self):
        ''' Test student access to views '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:create')
        self.assert200('courses:ranks')

        # 404 unless SiteConfig has marks turned on
        self.assert404('courses:my_marks')
        self.assert404('courses:marks', args=[self.test_student1.id])

        # Staff access only
        self.assert403('courses:join', args=[self.test_student1.id])
        self.assert403('courses:end_active_semester')
        self.assert403('courses:coursestudent_delete', args=[1])

        self.assert403('courses:markranges')
        self.assert403('courses:markrange_create')
        self.assert403('courses:markrange_update', args=[1])
        self.assert403('courses:markrange_delete', args=[1])

        self.assert403('courses:semester_list')
        self.assert403('courses:semester_create')
        self.assert403('courses:semester_update', args=[1])
        self.assert403('courses:semester_delete', args=[1])

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

        self.assert200('courses:markranges')
        self.assert200('courses:markrange_create')
        self.assert200('courses:markrange_update', args=[1])
        self.assert200('courses:markrange_delete', args=[1])

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

    def test_CourseStudentCreate_view(self):
        '''Students can register themselves in a course. Illegally accessing the registration view after registering will give an error 403'''
        self.client.force_login(self.test_student1)

        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)

        self.assertRedirects(response, reverse('quests:quests'))
        # Student should now be registered in a course
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # Now try acessing page a second time, should give 403 permission denied:
        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)
        self.assertEqual(response.status_code, 403)

    def test_CourseStudentCreate__simple_registration_hidden_fields(self):
        """
        If simplified_course_registration is enabled in siteconfig, fields in student registration form with only one viable option should be
        hidden and default to that value
        """
        # login test student and assert no courses
        self.client.force_login(self.test_student1)
        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        # enable simplified_course_registration in siteconfig
        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()

        # by default, Course/Block have 2 objects defined and will be visible
        # semester field is always hidden if simple registration = True, because it inherits one value from siteconfig.active_semester
        self.assertEqual(Course.objects.count(), 2)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Semester.objects.count(), 1)

        # accessing student registration view with all 3 fields hidden will automatically attempt to create/get CourseStudent object and redirect,
        # so access view in 2 steps to verify fields are hidden as intended

        # set one course object to inactive so only block field is visible
        toggle_course = Course.objects.first()
        toggle_course.active = False
        toggle_course.save()

        # access view and assert course, semester fields are hidden while block is visible
        response = self.client.get(reverse('courses:create'))

        # select = visible selection field
        self.assertEqual(response.context['form'].fields['course'].widget.input_type, 'hidden')
        self.assertEqual(response.context['form'].fields['block'].widget.input_type, 'select')
        self.assertEqual(response.context['form'].fields['semester'].widget.input_type, 'hidden')

        # re-activate course object, de-activate one block object
        toggle_course.active = True
        toggle_course.save()
        toggle_block = Block.objects.first()
        toggle_block.active = False
        toggle_block.save()

        # access view and assert course field is visible while other two are hidden
        response = self.client.get(reverse('courses:create'))

        # select = visible selection field
        self.assertEqual(response.context['form'].fields['course'].widget.input_type, 'select')
        self.assertEqual(response.context['form'].fields['block'].widget.input_type, 'hidden')
        self.assertEqual(response.context['form'].fields['semester'].widget.input_type, 'hidden')

    def test_CourseStudentCreate__simple_registration_auto_submit(self):
        """
        If simplified_course_registration is enabled and all student registration fields are hidden (1 option), accessing CourseStudentCreate view
        should automatically create corresponding CourseStudent object and redirect to quests page without accessing form

        <<< WIP: illegally re-accessing student registration tab will 403 via a future PR >>>
        Accessing the registration again through url editing should redirect to quests without creating new object
        """
        # login test student and assert no courses
        self.client.force_login(self.test_student1)
        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

        # enable simplified_course_registration in siteconfig
        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()

        # by default, 2 block and course objects exist but we can delete 1 of each because we won't access later
        Block.objects.first().delete()
        Course.objects.first().delete()

        # accessing reverse(courses:create) should now automatically create a CourseStudent object (none currently exist) and redirect to quests
        response = self.client.get(reverse('courses:create'))  # no form data necessary, all fields are hiddeninput with assigned defaults

        # assert redirect to quests page and CourseStudent object creation
        self.assertRedirects(response, reverse('quests:quests'))
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        # accessing the registration page a second time (illegally through url editing, etc.) should give 403 permission denied
        response = self.client.get(reverse('courses:create'))

        # assert permission denied and no new object created
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)


class MarkRangeViewTests(ViewTestUtilsMixin, TenantTestCase):
    """Test module for the MarkRange model's view classes"""

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password='password', is_staff=True)

        # set form data in setUp to be used for posting to create/update forms
        # manytomany field in MarkRange form prevents generate_form_data from functioning properly so must be set manually
        self.data = {
            'name': 'TestMarkRange',
            'minimum_mark': '72.5',
            'active': True,
            'color_light': '#BEFFFA',
            'color_dark': '#337AB7',
            'days': '1,2,3,4,5,6,7',
        }

    def test_MarkRangeList_view(self):
        """The MarkRange list view's object list should contain all MarkRange objects"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # get response from list view and assert all default existing MarkRanges are displayed
        response = self.client.get(reverse('courses:markranges'))
        self.assertQuerysetEqual(response.context['object_list'], MarkRange.objects.all())

    def test_MarkRangeCreate_view(self):
        """Staff users can create new MarkRange objects through the create view form"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # post to create form with data created in setUp
        response = self.client.post(reverse('courses:markrange_create'), data=self.data)

        # assert form redirects to list view and that new MarkRange object exists (creation successful)
        self.assertRedirects(response, reverse('courses:markranges'))
        self.assertTrue(MarkRange.objects.filter(name="TestMarkRange").exists())

    def test_MarkRangeUpdate_view(self):
        """Staff users can edit existing MarkRange objects through the update view form"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # post to update form with data created in setUp, updating MarkRange object with id=1
        response = self.client.post(reverse('courses:markrange_update', args=[1]), data=self.data)

        # assert form redirects to list view and that MarkRange object with id=1 has updated name (update successful)
        self.assertRedirects(response, reverse('courses:markranges'))
        self.assertEqual(MarkRange.objects.get(id=1).name, "TestMarkRange")

    def test_MarkRangeDelete_view(self):
        """Staff users can delete MarkRange objects through the delete view"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # assert MarkRange object with id=1 exists prior to deletion
        self.assertTrue(MarkRange.objects.filter(id=1).exists())

        # post to delete view deleting object with id=1
        response = self.client.post(reverse('courses:markrange_delete', args=[1]))

        # assert deletion redirectes to list view and that MarkRange object with id=1 doesn't exist (deletion successful)
        self.assertRedirects(response, reverse('courses:markranges'))
        self.assertFalse(MarkRange.objects.filter(id=1).exists())


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
            self.assertContains(response, str(obj))
            self.assertContains(response, obj.num_days())
            self.assertContains(response, obj.excludeddate_set.count())

    def test_SemesterCreate__without_ExcludedDates__view(self):
        self.client.force_login(self.test_teacher)

        post_data = {
            'name': 'semester', 'first_day': '2020-10-15', 'last_day': '2020-12-15',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }
        response = self.client.post(reverse('courses:semester_create'), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.count(), 2)
        self.assertTrue(Semester.objects.filter(name='semester').exists())

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

    def test_SemesterDelete_view(self):
        """ Admin should be able to delete a semester, as long as:
            - it is not the active semester
            - it has no coursesstudent objects (students registered in a course in the semester)
            - it is not closes
            ^ However, all of the above 3 exceptions are checked in the template and not in the view
        """
        self.client.force_login(self.test_teacher)
        semester = baker.make(Semester)

        response = self.client.post(reverse('courses:semester_delete', args=[semester.pk]))
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertFalse(Semester.objects.filter(pk=semester.pk).exists())


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
        self.assert403('courses:mark_distribution_chart', args=[self.teacher.pk])

    def test_ajax_status_code_for_anonymous(self):
        # checks redirect with ajax style request "HTTP_X_REQUESTED_WITH='XMLHttpRequest'"
        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)

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


class TestAjax_ProgressChart(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        self.student = baker.make(User)
        self.block = baker.make(Block)
        self.course = baker.make(Course)

        # freeze_time doesnt affect "SiteConfig.get().active_semester"
        # we have to manually set the dates
        self.semester = SiteConfig.get().active_semester
        self.semester.first_day = datetime.date(2024, 1, 1)  # keep in mind this is in localtime
        self.semester.last_day = self.semester.first_day + datetime.timedelta(days=135)
        self.semester.save()

        self.student_course = baker.make(
            CourseStudent,
            user=self.student,
            semester=self.semester,
            course=self.course,
            block=self.block
        )

        # use this to make aware datetime objects
        # (UTC-8) for datetime.date(2024, 1, 1)
        self.tz = timezone.get_default_timezone()
        self.base_xp = 1

    def create_quest_and_submissions(self, xp, quest_submission_date, quest_submission_quantity=1):
        """
        Creates and returns quest with linked quest submission objects for self.user

        Args:
            xp (int): amount of xp quest object will have,
            quest_submission_date: when the submission is approved
            quest_submission_quantity (int, optional): how many submissions are created. Defaults to 1.

        Returns:
            tuple[Quest, list[QuestSubmission]]: tuple of Quest object + list of QuestSubmission objects
        """

        quest = baker.make('quest_manager.Quest', xp=xp)
        quest_submissions = baker.make(
            'quest_manager.QuestSubmission',
            quest=quest,
            user=self.student,
            is_completed=True,
            is_approved=True,
            semester=self.semester,
            time_approved=quest_submission_date,
            _quantity=quest_submission_quantity,
        )

        return quest, quest_submissions

    def test_non_ajax_status_code(self):
        """ 403 unless verified ajax POST request """
        self.assert403('courses:ajax_progress_chart', args=[self.student.pk])

    def test_ajax_status_code_for_anonymous(self):
        """ checks redirect with ajax style request "HTTP_X_REQUESTED_WITH='XMLHttpRequest'"
        redirects because of LoginRequiredMixin
        """
        # post
        response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)
        # get
        response = self.client.get(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)

    def test_ajax_status_code_for_student(self):
        self.client.force_login(self.student)

        # post
        response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

        # get
        response = self.client.get(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 404)

    def test_ajax_xp_data__correct_xp_current_day(self):
        """ tests if xp_data from ajax request holds the correct xp on different days of the week.
        uses freeze_time to test the current day as Fri, Sat, Sun, and Mon
        """
        self.client.force_login(self.student)

        # create submissions from mon to fri
        starting_date = datetime.datetime(2024, 1, 1, tzinfo=self.tz)
        for i in range(5):
            self.create_quest_and_submissions(
                self.base_xp,
                starting_date + datetime.timedelta(days=i),
            )
        initial_xp = self.base_xp * 5  # xp * (5 submissions)

        # test for correct xp on week day
        # 2024-1-12 (Friday)
        with freeze_time(datetime.datetime(2024, 1, 5, 6, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 4)  # 4 == Friday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            # total xp should equal 5
            # (1 quest per day. 5th day)
            total_xp = json.loads(response.content)['xp_data'][-1]['y']
            self.assertEqual(total_xp, initial_xp)

        # create a submission on saturday
        saturday_xp = self.base_xp * 5
        self.create_quest_and_submissions(
            saturday_xp,
            datetime.datetime(2024, 1, 6, tzinfo=self.tz)
        )

        # XP earned in SAT + SUN while being on a week end will add the xp to Friday
        # test for correct xp on week end
        # does not test for "if today.weekday() in [5, 6]:  # SAT or SUN"
        # 2024-1-7 (Sunday)
        with freeze_time(datetime.datetime(2024, 1, 7, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 6)  # 6 == Sunday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            total_xp = json.loads(response.content)['xp_data'][-1]['y']
            self.assertEqual(total_xp, initial_xp + saturday_xp)

        # create a submission on sunday
        sunday_xp = saturday_xp
        self.create_quest_and_submissions(
            sunday_xp,
            datetime.datetime(2024, 1, 7, tzinfo=self.tz)
        )

        # XP earned in SAT + SUN while being on a week end will add the xp to Friday
        # test for correct xp on week end
        # tests for "if today.weekday() in [5, 6]:  # SAT or SUN"
        # 2024-1-14 (Sunday)
        with freeze_time(datetime.datetime(2024, 1, 7, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 6)  # 6 == Sunday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            total_xp = json.loads(response.content)['xp_data'][-1]['y']
            self.assertEqual(total_xp, initial_xp + saturday_xp + sunday_xp)

        # XP that was added on Friday should now be added to Monday
        # 2024-1-15 (Monday)
        with freeze_time(datetime.datetime(2024, 1, 8, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 0)  # 0 == Monday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            total_xp = json.loads(response.content)['xp_data'][-1]['y']
            self.assertEqual(total_xp, initial_xp + saturday_xp + sunday_xp)

    def test_ajax_xp_data__equals_xp_cache_on_weekend(self):
        """ test if the xp_data equals xp on weekend """
        self.client.force_login(self.student)

        # exclude monday to check if excluded date
        baker.make(
            'courses.ExcludedDate',
            semester=self.semester,

            # use datetime.date instead of datetime.datetime
            # see the "Anything Else?" section "Bug 2"
            # https://github.com/bytedeck/bytedeck/pull/1606
            date=datetime.date(2024, 1, 15),
        )

        # submission on saturday
        self.create_quest_and_submissions(
            self.base_xp,
            datetime.datetime(2024, 1, 13, tzinfo=self.tz)
        )
        # profile.xp_cached == 0 without doing this
        self.student.profile.xp_invalidate_cache()

        # test if the xp_data equals xp on weekend
        with freeze_time(datetime.datetime(2024, 1, 13, 6, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 5)  # 5 == Saturday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            total_xp = json.loads(response.content)['xp_data'][-1]['y']
            self.assertEqual(total_xp, self.base_xp)  # 1 xp since only 1 submission
            self.assertEqual(total_xp, self.student.profile.xp_cached)

        # submission on monday
        self.create_quest_and_submissions(
            self.base_xp,
            datetime.datetime(2024, 1, 14, tzinfo=self.tz)
        )

        # update the cache
        self.student.profile.xp_invalidate_cache()

        # test if the xp_data on monday is correct using xp_cached
        with freeze_time(datetime.datetime(2024, 1, 15, 6, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 0)  # 0 == Monday
            response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

            json_data = json.loads(response.content)
            total_xp = json_data['xp_data'][-1]['y']
            valid_days = json_data['xp_data'][-1]['x']

            # test xp
            self.assertEqual(total_xp, self.base_xp * 2)  # 2x because 2 quest submissions with self.base_xp
            self.assertEqual(total_xp, self.student.profile.xp_cached)

            # test if monday was actually excluded from the json_data
            # first_day (2024/1/1), today is (2024/1/15). Means, SUN/SAT + SUN/SAT/MONDAY was excluded
            # giving 10 valid days
            self.assertEqual(valid_days, 10)


class MarkCalculationsViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.student = baker.make(User)

        self.block = baker.make(Block)
        self.course = baker.make(Course, xp_for_100_percent=1000)

        self.stu_course = baker.make(
            CourseStudent,
            user=self.student,
            semester=SiteConfig.get().active_semester,
            block=self.block,
            course=self.course,
        )

        # to show mark calculation page without 404 you need to turn this on
        siteconfig = SiteConfig.get()
        siteconfig.display_marks_calculation = True
        siteconfig.save()

    @patch('courses.models.Semester.fraction_complete')
    def test_current_mark_ranges_by_xp__correct_values(self, mock_sem_fraction_complete):
        """
        tests the markranges displayed under "Current Mark Ranges by XP" are correct based on the percentage of the semester completed.
        specifically tests when semester is 0%, 50%, 75%, 100%, and 125% done.
        """
        self.client.force_login(self.student)

        # default markranges from initialization
        # pass.minimum_mark = 0.495
        # B.minimum_mark = 0.725
        # A.minimum_mark = 0.855

        # Check if markranges show 0% of 1000 xp
        mock_sem_fraction_complete.return_value = 0
        response = self.client.get(reverse('courses:my_marks'))
        self.assertContains(response, '0')  # XP should be 0 for all ranges

        # Check if markranges show as 50% of 1000 xp
        mock_sem_fraction_complete.return_value = 0.5
        response = self.client.get(reverse('courses:my_marks'))
        self.assertTrue(mock_sem_fraction_complete.called)

        self.assertEqual(1000 * mock_sem_fraction_complete.return_value, 500)
        self.assertContains(response, '247')  # 500 * 0.495 = 247.5
        self.assertContains(response, '362')  # 500 * 0.725 = 362.5
        self.assertContains(response, '427')  # 500 * 0.855 = 427.5

        # Check if markranges show as 75% of 1000 xp
        mock_sem_fraction_complete.return_value = 0.75
        response = self.client.get(reverse('courses:my_marks'))

        self.assertEqual(1000 * mock_sem_fraction_complete.return_value, 750)
        self.assertContains(response, '371')  # 750 * 0.495 = 371.25
        self.assertContains(response, '543')  # 750 * 0.725 = 543.75
        self.assertContains(response, '641')  # 750 * 0.855 = 641.25

        # Check if markranges show as 100% of 1000 xp
        mock_sem_fraction_complete.return_value = 1
        response = self.client.get(reverse('courses:my_marks'))

        self.assertEqual(1000 * mock_sem_fraction_complete.return_value, 1000)
        self.assertContains(response, '495')  # 1000 * 0.495 = 495
        self.assertContains(response, '725')  # 1000 * 0.725 = 725
        self.assertContains(response, '855')  # 1000 * 0.855 = 855

        # Test for over 100% completion
        mock_sem_fraction_complete.return_value = 1.25
        response = self.client.get(reverse('courses:my_marks'))
        self.assertContains(response, '618')  # 1250 * 0.495 = 618.75
        self.assertContains(response, '906')  # 1250 * 0.725 = 906.25
        self.assertContains(response, '1068')  # 1250 * 0.855 = 1068.75


class AjaxRankPopupTests(ViewTestUtilsMixin, TenantTestCase):
    """ test case for
    + ajax/on_show_ranked_popup/
    + ajax/on_close_ranked_popup/
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.student = baker.make(User)

    def test_status_codes(self):
        ''' tests correct status codes for `on_show_ranked_popup` and `on_close_ranked_popup`
        403 - because not ajax
        302 - because of not logged in (LoginRequiredMixin)
        200 - success
        '''

        # test anon
        # ajax_on_show_ranked_popup
        self.assert403('courses:ajax_on_show_ranked_popup')
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)

        # ajax_on_close_ranked_popup
        self.assert403('courses:ajax_on_close_ranked_popup')
        response = self.client.get(reverse('courses:ajax_on_close_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)

        # test student
        self.client.force_login(self.student)

        # ajax_on_show_ranked_popup
        self.assert403('courses:ajax_on_show_ranked_popup')
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

        # ajax_on_close_ranked_popup
        self.assert403('courses:ajax_on_close_ranked_popup')
        response = self.client.get(reverse('courses:ajax_on_close_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    def test_on_show_ranked_popup(self):
        """ Checks if earned_rank and next_rank are correct when requesting json from ranked popups
        """
        # make sure theres enough initial ranks for test
        # first (0), second (20), third (60)
        # cant get notification for first, so get second and third
        self.assertTrue(Rank.objects.count() >= 3)
        earned_rank = Rank.objects.get_next_rank(1)
        next_rank = Rank.objects.get_next_rank(earned_rank.xp)

        # RankPopup needs the notification and correct xp_cached
        notify_rank_up(self.student, 0, earned_rank.xp)
        self.student.profile.xp_cached = earned_rank.xp
        self.student.profile.save()

        # login and get context from response
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        context = response.context

        # check if context has the correct ranks
        self.assertEqual(context['earned_rank'], earned_rank)
        self.assertEqual(context['next_rank'], next_rank)

    def test_on_show_ranked_popup__no_notification(self):
        """ Check if when no notifications, ranked popup has no html to show and show=False
        """
        # clear all notifications
        Notification.objects.all().mark_all_read(self.student)
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 0)

        # login and get json response
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        json_data = json.loads(response.content)

        # check if "show=False" and if html is empty
        self.assertFalse(json_data['show'])
        self.assertFalse(json_data['html'])

    def test_on_show_ranked_popup__on_last_rank(self):
        """ Check if the next_rank is None when achieving the highest possible rank
        """
        self.assertTrue(Rank.objects.count() >= 2)
        earned_rank = Rank.objects.all().last()
        next_rank = None

        # RankPopup needs the notification and correct xp_cached
        notify_rank_up(self.student, 0, earned_rank.xp)
        self.student.profile.xp_cached = earned_rank.xp
        self.student.profile.save()

        # login and get context from response
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        context = response.context

        # check if context has the correct ranks
        self.assertEqual(context['earned_rank'], earned_rank)
        self.assertEqual(context['next_rank'], next_rank)

    def test_on_show_ranked_popup__multiple_ranked_notifications(self):
        """ Check if the popup only shows the latest notification (newest rank)
        """
        # make sure theres enough initial ranks for test
        self.assertTrue(Rank.objects.count() >= 4)
        previous_rank = Rank.objects.get_next_rank(1)
        earned_rank = Rank.objects.get_next_rank(previous_rank.xp)
        next_rank = Rank.objects.get_next_rank(earned_rank.xp)

        # RankPopup needs the notification and correct xp_cached
        notify_rank_up(self.student, 0, previous_rank.xp)
        notify_rank_up(self.student, 0, earned_rank.xp)
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 2)
        self.student.profile.xp_cached = earned_rank.xp
        self.student.profile.save()

        # login and get context from response
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:ajax_on_show_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        context = response.context

        # check if context has the correct ranks
        self.assertEqual(context['earned_rank'], earned_rank)
        self.assertNotEqual(context['earned_rank'], previous_rank)
        self.assertEqual(context['next_rank'], next_rank)

    def test_on_close_ranked_popup(self):
        """ Check if 'courses:ajax_on_show_ranked_popup' closes only the latest ranked notification
        """
        # create 2 rank up notifications
        # one should be older than the other
        notify_rank_up(self.student, 0, 500)
        notify_rank_up(self.student, 0, 1000)
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 2)

        # trigger the ajax response
        self.client.force_login(self.student)
        self.client.get(reverse('courses:ajax_on_close_ranked_popup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        # check if it was marked as read
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 1)
