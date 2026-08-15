from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.shortcuts import reverse
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import get_public_schema_name
from django.utils import timezone

from model_bakery import baker
from freezegun import freeze_time

from courses.forms import CourseStudentStaffForm, ExcludedDateFormset, SemesterForm
from courses.models import Block, Course, CourseStudent, MarkRange, Semester, Rank, ExcludedDate
from courses.views import SemesterActivate, SemesterUpdate
from quest_manager.models import Quest, QuestSubmission
from badges.models import Badge, BadgeAssertion
from notifications.models import Notification, notify_rank_up
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, generate_form_data, model_to_form_data, generate_formset_data
from siteconfig.models import SiteConfig
from djcytoscape.models import CytoScape

import random
import datetime
import itertools
import json

User = get_user_model()


class RankViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and a student for the rank view tests."""
        # need a teacher and a student so tests can log in as each with force_login()

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student1 = User.objects.create_user('test_student')

    def test_all_rank_page_status_codes__anonymous_redirected(self):
        ''' If not logged in then all views should redirect to login page '''

        self.assertRedirectsLogin('courses:ranks')
        self.assertRedirectsLogin('courses:rank_create')
        self.assertRedirectsLogin('courses:rank_update', args=[1])
        self.assertRedirectsLogin('courses:rank_delete', args=[1])

    def test_all_rank_page_status_codes__students(self):
        ''' If logged in as student then all views except ranks list view should redirect to login page '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:ranks')

        # staff access only
        self.assert403('courses:rank_create')
        self.assert403('courses:rank_update', args=[1])
        self.assert403('courses:rank_delete', args=[1])

    def test_all_rank_page_status_codes__staff(self):
        ''' If logged in as staff then all views should return code 200 for successful retrieval of page '''
        self.client.force_login(self.test_teacher)

        self.assert200('courses:ranks')
        self.assert200('courses:rank_create')
        self.assert200('courses:rank_update', args=[1])
        self.assert200('courses:rank_delete', args=[1])

    def test_RanksList_view__accessible_when_logged_in(self):
        """ Admin and students should be able to view ranks. Anonymous users should be asked to login if they attempt to view ranks. """

        # Anonymous user
        self.assertRedirectsLogin('courses:ranks')

        # student
        self.client.force_login(self.test_student1)
        self.assert200('courses:ranks')

        # teacher
        self.client.force_login(self.test_teacher)
        response = self.assert200('courses:ranks')

        # Should contain 13 default ranks e.g. Digital Novice, Digital Ameteur II, etc
        self.assertEqual(response.context['object_list'].count(), 13)

    def test_RankCreate_view__staff_can_create(self):
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

    def test_RankUpdate_view__staff_can_update(self):
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

    def test_RankDelete_view__staff_can_delete(self):
        """ Admin should be able to delete a rank """
        self.client.force_login(self.test_teacher)

        before_delete_count = Rank.objects.count()
        response = self.client.post(reverse('courses:rank_delete', args=[1]))
        after_delete_count = Rank.objects.count()
        self.assertRedirects(response, reverse('courses:ranks'))
        self.assertEqual(before_delete_count - 1, after_delete_count)

    def test_scape_update_message__on_update_and_delete(self):
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
        self.assertIn(scape.name, str(messages[0]))

        # to clear any messages before next test
        self.assert200('courses:ranks')

        # test messages for quest_delete
        response = self.client.post(reverse('courses:rank_delete', args=[rank.id]))
        messages = list(response.wsgi_request._messages)  # unittest dont carry messages when redirecting
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(messages), 1)
        self.assertIn(scape.name, str(messages[0]))


class CourseViewTestData:
    """Shared fixtures for the Course / CourseStudent view tests: a teacher, a student, the active
    semester plus a block/course/grade, and valid registration form data.

    A plain mixin (not a TestCase) so the test runner doesn't collect it as an empty test class.
    """

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, student, block, course and grade plus valid registration form data."""
        # need a teacher and a student so tests can log in as each with force_login()

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student1 = User.objects.create_user('test_student')

        cls.sem = SiteConfig.get().active_semester
        cls.block = baker.make('courses.block')
        cls.course = baker.make('courses.course')
        cls.grade = baker.make('courses.grade')

        cls.valid_form_data = {
            'semester': cls.sem.pk,
            'block': cls.block.pk,
            'course': cls.course.pk,
        }


class CourseViewTests(CourseViewTestData, ByteDeckTenantTestCase):

    def test_all_page_status_codes__anonymous_redirected(self):
        ''' If not logged in then all views should redirect to home page '''
        self.assertRedirectsLogin('courses:create')
        self.assertRedirectsLogin('courses:join', args=[1])
        self.assertRedirectsLogin('courses:coursestudent_delete', args=[1])
        self.assertRedirectsLogin('courses:ranks')
        self.assertRedirectsLogin('courses:my_marks')
        self.assertRedirectsLogin('courses:marks', args=[1])
        self.assertRedirectsLogin('courses:semester_archive', args=[1])

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

    def test_all_page_status_codes__students(self):
        ''' Test student access to views '''
        self.client.force_login(self.test_student1)
        self.assert200('courses:create')
        self.assert200('courses:ranks')

        # 404 unless SiteConfig has marks turned on
        self.assert404('courses:my_marks')
        self.assert404('courses:marks', args=[self.test_student1.id])

        # Staff access only
        self.assert403('courses:join', args=[self.test_student1.id])
        self.assert403('courses:semester_archive', args=[1])
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

    def test_all_page_status_codes__staff(self):
        """Staff get 200 on all course management views."""
        self.client.force_login(self.test_teacher)

        # Staff access only
        self.assert200('courses:join', args=[self.test_student1.id])

        self.assert200('courses:semester_archive', args=[SiteConfig.get().active_semester.id])

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

    def test_course_student_update__status_codes(self):
        """The CourseStudent update view is login-required, staff-only (403 for students, 200 for staff)."""
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

    def test_SemesterArchive__staff_post_archives(self):
        """POSTing the archive view closes the active semester and redirects to the semester list."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        self.assertFalse(active_sem.is_archived)
        self.assertRedirects(
            response=self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id])),
            expected_url=reverse('courses:semester_list'),
        )
        active_sem.refresh_from_db()
        self.assertTrue(active_sem.is_archived)

    def test_SemesterArchive__get_is_a_preview_and_does_not_archive(self):
        """GET on the archive view renders the confirmation/preview page (with the counts of
        what archiving will do) without changing anything."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        student = baker.make(User)
        baker.make(CourseStudent, user=student, course=baker.make(Course), semester=active_sem)

        response = self.client.get(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['semester'], active_sem)
        self.assertEqual(response.context['num_registrations'], 1)
        self.assertEqual(response.context['num_seats_freed'], 1)
        self.assertFalse(response.context['blocked'])
        active_sem.refresh_from_db()
        self.assertFalse(active_sem.is_archived)

    def test_SemesterArchive__get_shows_blockers(self):
        """The archive preview lists blockers: submissions awaiting approval and students
        with negative XP, with the form replaced by a link back to the semester list."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        baker.make(QuestSubmission, is_completed=True, is_approved=False, semester=active_sem)
        negative_student = baker.make(User)
        baker.make(CourseStudent, user=negative_student, course=baker.make(Course),
                   semester=active_sem, xp_adjustment=-10)

        response = self.client.get(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['blocked'])
        self.assertEqual(response.context['num_awaiting_approval'], 1)
        self.assertIn(negative_student, response.context['negative_xp_users'])

    def test_SemesterArchive__post_blocked_by_pending_approvals(self):
        """POSTing the archive view while quest submissions still await approval warns
        and leaves the semester open (the preview shows the blocker, but the POST must
        also refuse in case the state changed after the preview was rendered)."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        baker.make(QuestSubmission, is_completed=True, is_approved=False, semester=active_sem)

        response = self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertWarningMessage(response)
        self.assertIn('awaiting approval', str(self.get_message_list(response)[0]))
        active_sem.refresh_from_db()
        self.assertFalse(active_sem.is_archived)

    def test_SemesterArchive__already_archived(self):
        """POSTing the archive view for an already-archived semester is refused and takes no
        action: its final marks are recorded and must not be recalculated."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester
        active_sem.status = Semester.Status.ARCHIVED
        active_sem.save()

        response = self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertErrorMessage(response)

    def test_SemesterArchive__semester_not_open_get(self):
        """A semester that isn't open has nothing to preview archiving, so staff are sent
        back to the semester list with an error."""
        self.client.force_login(self.test_teacher)
        semester_id = SiteConfig.get().active_semester.id
        Semester.objects.complete_semester()
        self.assertIsNone(SiteConfig.get().active_semester)

        response = self.client.get(reverse('courses:semester_archive', args=[semester_id]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertErrorMessage(response)
        self.assertIn('nothing to archive', str(self.get_message_list(response)[0]))

    def test_SemesterArchive__upcoming_semester_post(self):
        """An upcoming semester is refused too: nobody has earned anything in it yet, so
        there are no final marks to record."""
        self.client.force_login(self.test_teacher)
        upcoming = baker.make(Semester, status=Semester.Status.UPCOMING)

        response = self.client.post(reverse('courses:semester_archive', args=[upcoming.id]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertErrorMessage(response)
        upcoming.refresh_from_db()
        self.assertTrue(upcoming.is_upcoming)

    def test_SemesterArchive__leaves_the_deck_with_no_open_semester(self):
        """Archiving is how a deck gets to the between-semesters state (issue #1177): the
        semester is archived and nothing is active, so students can't join a course."""
        self.client.force_login(self.test_teacher)
        active_sem = SiteConfig.get().active_semester

        self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

        active_sem.refresh_from_db()
        self.assertTrue(active_sem.is_archived)
        self.assertIsNone(SiteConfig.get().active_semester)
        self.assertTrue(SiteConfig.get().has_no_open_semester())

    def test_SemesterArchive__announcements_opt_out(self):
        """Archiving without the archive_announcements checkbox leaves announcements alone."""
        from announcements.models import Announcement
        announcement = baker.make(Announcement, archived=False, draft=False)
        self.client.force_login(self.test_teacher)

        response = self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))  # no checkbox in POST data

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertSuccessMessage(response)
        announcement.refresh_from_db()
        self.assertFalse(announcement.archived)

    def test_SemesterActivate__changes_active_semester(self):
        """POSTing the activate view changes the siteconfig's active semester and
        redirects to the semester_list. Starting an upcoming semester also opens it,
        so students can join a course in it."""
        self.client.force_login(self.test_teacher)
        new_semester = baker.make('courses.semester', status=Semester.Status.UPCOMING)
        response = self.client.post(reverse('courses:semester_activate', args=[new_semester.pk]))
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(SiteConfig.get().active_semester, Semester.objects.get(pk=new_semester.pk))
        new_semester.refresh_from_db()
        self.assertTrue(new_semester.is_open)

    def test_SemesterActivate__already_open_semester_stays_open(self):
        """Activating a semester that is already open just points the deck at it: the
        status is untouched, so re-activating never rewinds an archived-or-open stage."""
        self.client.force_login(self.test_teacher)
        open_semester = baker.make('courses.semester', status=Semester.Status.OPEN)

        response = self.client.post(reverse('courses:semester_activate', args=[open_semester.pk]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(SiteConfig.get().active_semester, open_semester)
        open_semester.refresh_from_db()
        self.assertTrue(open_semester.is_open)

    def test_SemesterActivate__starts_the_next_semester_after_a_pause(self):
        """Activating a semester is the way out of the between-semesters state: the deck has
        an open semester again and students can join a course."""
        self.client.force_login(self.test_teacher)
        Semester.objects.complete_semester()
        next_semester = baker.make('courses.semester', status=Semester.Status.UPCOMING)

        response = self.client.post(reverse('courses:semester_activate', args=[next_semester.pk]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(SiteConfig.get().active_semester, next_semester)
        self.assertFalse(SiteConfig.get().has_no_open_semester())

    def test_SemesterActivate__archived_semester_is_refused(self):
        """Archiving is one-way: an archived semester can't be reopened, since its students'
        final marks have already been recorded."""
        self.client.force_login(self.test_teacher)
        archived = baker.make('courses.semester', status=Semester.Status.ARCHIVED)
        original_active = SiteConfig.get().active_semester

        response = self.client.post(reverse('courses:semester_activate', args=[archived.pk]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(str(self.get_message_list(response)[0]), SemesterActivate.ARCHIVED_SEMESTER_ERROR)
        archived.refresh_from_db()
        self.assertTrue(archived.is_archived)
        self.assertEqual(SiteConfig.get().active_semester, original_active)

    def test_SemesterActivate__get_not_allowed(self):
        """GET must not change the active semester (deck-wide state changes are POST-only,
        so they can't be triggered by link prefetching or a cross-site GET): it returns
        405 Method Not Allowed and leaves the active semester untouched."""
        self.client.force_login(self.test_teacher)
        original_active = SiteConfig.get().active_semester
        new_semester = baker.make('courses.semester')
        response = self.client.get(reverse('courses:semester_activate', args=[new_semester.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(SiteConfig.get().active_semester, original_active)

    def test_CourseList_view__staff_can_view(self):
        """ Admin should be able to view course list """
        self.client.force_login(self.test_teacher)
        response = self.assert200('courses:course_list')

        # Should contain Default and another one via bake
        self.assertEqual(response.context['object_list'].count(), 2)

    def test_CourseCreate_view__staff_can_create(self):
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

    def test_CourseUpdate_view__staff_can_update(self):
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
        self.client.force_login(self.test_teacher)

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


class CourseStudentViewTests(CourseViewTestData, ByteDeckTenantTestCase):

    def test_CourseStudentUpdate_view__staff_can_update(self):
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

    def test_CourseAddStudent_view__staff_can_add(self):
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

        # GRADE field is depercated and no longer used within unique_together

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

    def test_CourseStudentDelete_view__teacher_can_delete(self):
        """ Teacher should be able to delete a student from a course (StudentCourse object)
        and should redirect to the student's profile when complete. """
        self.client.force_login(self.test_teacher)
        course_student = baker.make(CourseStudent, user=self.test_student1)

        # can access the Delete View
        self.assert200('courses:coursestudent_delete', args=[course_student.id])

        before_delete_count = CourseStudent.objects.count()
        response = self.client.post(reverse('courses:coursestudent_delete', args=[course_student.id]))
        after_delete_count = CourseStudent.objects.count()
        self.assertRedirects(response, reverse('profiles:profile_detail', args=[self.test_student1.profile.id]))
        self.assertEqual(before_delete_count - 1, after_delete_count)

    def test_CourseStudentCreate_view__student_self_registers(self):
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

    def test_CourseStudentCreate_view__active_registration_in_old_semester_does_not_block(self):
        """A student with an active registration left over in an old (not-yet-closed) semester can
        still reach the registration view for the new active semester — no 403 (#1893). Previously
        any active registration blocked registration, so an unclosed old semester locked students
        out of joining courses in the new one."""
        self.client.force_login(self.test_student1)

        # Active registration left over in the original (now-old) semester.
        old_semester = SiteConfig.get().active_semester
        baker.make('courses.coursestudent', user=self.test_student1, semester=old_semester, active=True)

        # A new semester becomes active while the old one stays open (not closed).
        new_semester = baker.make('courses.semester')
        config = SiteConfig.get()
        config.active_semester = new_semester
        config.full_clean()
        config.save()

        # The stale active registration is in a different, still-open semester, so it must not 403.
        response = self.client.get(reverse('courses:create'))
        self.assertNotEqual(response.status_code, 403)

    def _close_active_semester(self):
        """Close the deck's active semester (leaving it as the active semester), reproducing the
        'no semester is open' state from issue #2060. Saving fires the SiteConfig cache invalidation.
        """
        active = SiteConfig.get().active_semester
        active.status = Semester.Status.ARCHIVED
        active.save()

    def test_CourseStudentCreate_view__blocked_when_no_open_semester__get(self):
        """When the active semester is closed, the join page shows a 'no semesters open' message
        instead of the registration form (issue #2060)."""
        self.client.force_login(self.test_student1)
        self._close_active_semester()

        response = self.client.get(reverse('courses:create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No semesters are currently open')
        self.assertNotContains(response, 'id="coursestudentform"')

    def test_CourseStudentCreate_view__blocked_when_no_open_semester__post(self):
        """A student can't register when the active semester is closed: POSTing valid data creates
        no CourseStudent and shows the 'no semesters open' message (issue #2060)."""
        self.client.force_login(self.test_student1)
        self._close_active_semester()

        response = self.client.post(reverse('courses:create'), data=self.valid_form_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No semesters are currently open')
        self.assertEqual(self.test_student1.coursestudent_set.count(), 0)

    def test_no_open_semester__student_join_button_replaced_by_message(self):
        """A student with no course sees a 'no semester open' note instead of the Join a Course
        button when the deck has no open semester (issue #2060)."""
        student = User.objects.create_user('no_course_student')  # no CourseStudent registration
        self._close_active_semester()
        self.client.force_login(student)

        response = self.client.get(reverse('quests:quests'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ask your teacher to open one')
        self.assertNotContains(response, 'Join a Course')

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

    def test_CourseStudentCreate__simple_registration_reuses_existing_membership(self):
        """When simplified auto-registration finds an existing (matching) membership, get_or_create
        returns created=False: the view still redirects but adds no 'added to' message and creates
        no duplicate row."""
        self.client.force_login(self.test_student1)

        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()

        # reduce to a single active block/course so the registration fields render hidden
        Block.objects.first().delete()
        Course.objects.first().delete()

        # a membership matching the auto-create lookup already exists; active=False so access
        # isn't blocked by the "already registered this semester" guard
        baker.make(
            CourseStudent,
            user=self.test_student1,
            semester=SiteConfig.get().active_semester,
            block=Block.objects.filter(active=True).first(),
            course=Course.objects.filter(active=True).first(),
            active=False,
        )
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)

        response = self.client.get(reverse('courses:create'))

        self.assertRedirects(response, reverse('quests:quests'))
        # existing row reused, not duplicated
        self.assertEqual(self.test_student1.coursestudent_set.count(), 1)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertFalse(any('added to' in m for m in messages))


class MarkRangeViewTests(ByteDeckTenantTestCase):
    """Test module for the MarkRange model's view classes"""

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and reusable MarkRange form data for create/update posts."""
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)

        # set form data in setUpTestData to be used for posting to create/update forms
        # manytomany field in MarkRange form prevents generate_form_data from functioning properly so must be set manually
        cls.data = {
            'name': 'TestMarkRange',
            'minimum_mark': '72.5',
            'active': True,
            'color_light': '#BEFFFA',
            'color_dark': '#337AB7',
            'days': '1,2,3,4,5,6,7',
        }

    def test_MarkRangeList_view__lists_all(self):
        """The MarkRange list view's object list should contain all MarkRange objects"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # get response from list view and assert all default existing MarkRanges are displayed
        response = self.client.get(reverse('courses:markranges'))
        self.assertQuerySetEqual(response.context['object_list'], MarkRange.objects.all())

    def test_MarkRangeCreate_view__staff_can_create(self):
        """Staff users can create new MarkRange objects through the create view form"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # post to create form with data created in setUp
        response = self.client.post(reverse('courses:markrange_create'), data=self.data)

        # assert form redirects to list view and that new MarkRange object exists (creation successful)
        self.assertRedirects(response, reverse('courses:markranges'))
        self.assertTrue(MarkRange.objects.filter(name="TestMarkRange").exists())

    def test_MarkRangeUpdate_view__staff_can_update(self):
        """Staff users can edit existing MarkRange objects through the update view form"""

        # login a teacher
        self.client.force_login(self.test_teacher)

        # post to update form with data created in setUp, updating MarkRange object with id=1
        response = self.client.post(reverse('courses:markrange_update', args=[1]), data=self.data)

        # assert form redirects to list view and that MarkRange object with id=1 has updated name (update successful)
        self.assertRedirects(response, reverse('courses:markranges'))
        self.assertEqual(MarkRange.objects.get(id=1).name, "TestMarkRange")

    def test_MarkRangeDelete_view__staff_can_delete(self):
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


class SemesterStatusBannerTests(ByteDeckTenantTestCase):
    """The staff-only semester status banner rendered on every page via base.html
    (semester_status_banner.html): nudges archiving an ended active semester (#2157)
    and warns when no semester is open for students to join (#1177)."""

    # the no-open-semester warning, of which there is only ever one
    BANNER_ID = 'semester-status-banner'

    @staticmethod
    def ended_banner_id(semester):
        """The id of the archive nudge for one semester.

        Several can render at once, one per ended semester, so each carries its semester's id.

        Returns:
            str: the id attribute that semester's nudge is rendered with.
        """
        return f'semester-status-banner-{semester.id}'

    @classmethod
    def setUpTestData(cls):
        """A teacher and a student for checking who sees the banner."""
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student')

    def test_semester_status_banner__hidden_while_active_semester_is_running(self):
        """No banner renders while the active semester is open and within its dates."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:semester_list'))
        self.assertNotContains(response, self.BANNER_ID)

    def test_semester_status_banner__active_semester_ended(self):
        """Once the active semester's last day has passed, staff see the archive nudge
        with a link to the archive confirmation page."""
        active_sem = SiteConfig.get().active_semester
        active_sem.first_day = datetime.date.today() - datetime.timedelta(days=100)
        active_sem.last_day = datetime.date.today() - datetime.timedelta(days=10)
        active_sem.save()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, self.ended_banner_id(active_sem))
        self.assertContains(response, 'ended on')
        self.assertContains(response, reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))

    def test_semester_status_banner__nudges_each_ended_semester_on_its_own(self):
        """With two semesters running (#1781), the nudge is per semester: the one that has
        ended is named and linked to its own archive page, and the one still running is left
        alone rather than being swept up with it."""
        ended = SiteConfig.get().active_semester
        ended.first_day = datetime.date.today() - datetime.timedelta(days=100)
        ended.last_day = datetime.date.today() - datetime.timedelta(days=10)
        ended.save()
        still_running = baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=datetime.date.today() - datetime.timedelta(days=10),
            last_day=datetime.date.today() + datetime.timedelta(days=10),
        )

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, self.ended_banner_id(ended))
        self.assertContains(response, f'Semester {ended} ended on')
        # the banner's own link, not the archive button every open row in the table already has
        archive_url = reverse('courses:semester_archive', args=[ended.id])
        self.assertContains(response, f'<a href="{archive_url}" class="alert-link">Archive it</a>')
        self.assertNotContains(response, self.ended_banner_id(still_running))
        self.assertNotContains(response, f'Semester {still_running} ended on')

    def test_semester_status_banner__gives_each_ended_semester_its_own_id(self):
        """Two ended semesters render two nudges, and each gets its own id: a page with the same
        id twice makes anything selecting it (a script, a screen reader landmark) see only the
        first, so one of the two nudges would effectively go missing."""
        first = SiteConfig.get().active_semester
        first.first_day = datetime.date.today() - datetime.timedelta(days=200)
        first.last_day = datetime.date.today() - datetime.timedelta(days=100)
        first.save()
        second = baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=datetime.date.today() - datetime.timedelta(days=90),
            last_day=datetime.date.today() - datetime.timedelta(days=10),
        )

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, self.ended_banner_id(first))
        self.assertContains(response, self.ended_banner_id(second))
        self.assertNotEqual(self.ended_banner_id(first), self.ended_banner_id(second))

    def test_semester_status_banner__no_open_semester(self):
        """When the active semester is archived (the no-open-semester state, #1177),
        staff see the students-can't-join warning linking to the semester list."""
        active_sem = SiteConfig.get().active_semester
        active_sem.status = Semester.Status.ARCHIVED
        active_sem.save()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, self.BANNER_ID)
        self.assertContains(response, 'No semester is open')

    def test_semester_status_banner__hidden_from_students(self):
        """Students never see the semester status banner, even in the states that show
        it to staff."""
        active_sem = SiteConfig.get().active_semester
        active_sem.status = Semester.Status.ARCHIVED
        active_sem.save()

        self.client.force_login(self.test_student)
        # any student-accessible page renders base.html; the quest list is the landing page
        response = self.client.get(reverse('quests:quests'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.BANNER_ID)

    def test_semester_status_banner__hidden_when_no_config(self):
        """On schemas without a SiteConfig (the config context processor supplies None on
        the public tenant), the banner renders nothing even for a staff user."""
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get('/')
        request.user = self.test_teacher
        html = render_to_string('semester_status_banner.html', {'config': None, 'request': request})

        self.assertNotIn(self.BANNER_ID, html)

    def test_semester_status_banner__hidden_on_suspended_deck(self):
        """A suspended deck shows only the suspension banner: the semester nudges are
        suppressed, since students can't sign in there anyway. Uses the deck owner because
        the suspension middleware signs everyone else out (#1734)."""
        active_sem = SiteConfig.get().active_semester
        active_sem.status = Semester.Status.ARCHIVED
        active_sem.save()

        # both clocks lapsed = suspended (tenant.is_suspended)
        self.tenant.trial_end_date = datetime.date(2020, 1, 1)
        self.tenant.paid_until = None
        self.tenant.save()

        self.client.force_login(SiteConfig.get().deck_owner)
        response = self.client.get(reverse('courses:semester_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.BANNER_ID)
        # the suspension banner is the one warning that must remain
        self.assertContains(response, 'This deck is suspended')


class SemesterViewTests(ByteDeckTenantTestCase):

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

    @classmethod
    def setUpTestData(cls):
        """Create a teacher for the class tests."""
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)

    def test_SemesterList_view__lists_semesters(self):
        """The semester list view renders each semester with its day counts and excluded-date counts."""
        self.client.force_login(self.test_teacher)

        response = self.assert200('courses:semester_list')
        self.assertEqual(response.context['object_list'].count(), 1)

        for obj in response.context['object_list']:
            self.assertContains(response, str(obj))
            self.assertContains(response, obj.num_days())
            self.assertContains(response, obj.excludeddate_set.count())

    def test_SemesterList_view__semester_without_dates(self):
        """The semester list page renders without errors when a semester has a blank
        name and no first/last day. Regression test for issue #912.
        """
        self.client.force_login(self.test_teacher)

        semester = baker.make(Semester, name='', first_day=None, last_day=None)
        response = self.assert200('courses:semester_list')
        self.assertContains(response, str(semester))

    def test_SemesterCreate__without_ExcludedDates__view(self):
        """Creating a semester with no excluded dates saves it and redirects to the list."""
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
        # The just-created semester is the most recent one; don't assume an
        # absolute pk (sequences aren't reset between reused-schema test classes).
        semester = Semester.objects.latest('id')

        self.assertTrue(semester.excludeddate_set.exists())
        for ed in semester.excludeddate_set.all():
            self.assertIn(ed.date, exclude_dates)

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

    def test_SemesterUpdate_view__updates_dates(self):
        """Posting new dates to the update view saves them to the semester."""
        self.client.force_login(self.test_teacher)

        post_data = {
            'first_day': '2020-10-16',
            'last_day': '2020-12-16',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }
        response = self.client.post(reverse('courses:semester_update', args=[1]), data=post_data)
        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertEqual(Semester.objects.get(id=1).first_day.strftime('%Y-%m-%d'), post_data['first_day'])

    def test_SemesterUpdate_view__archived_semester_is_blocked(self):
        """An archived semester's dates are what its students' final marks were calculated
        from, so the edit view refuses it (GET and POST alike) rather than rewriting a
        finished record. The list hides the button, but the URL is still reachable."""
        self.client.force_login(self.test_teacher)
        archived = baker.make(
            Semester, status=Semester.Status.ARCHIVED,
            first_day=datetime.date(2020, 1, 1), last_day=datetime.date(2020, 6, 1),
        )
        post_data = {
            'first_day': '2021-10-16',
            'last_day': '2021-12-16',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }

        get_response = self.client.get(reverse('courses:semester_update', args=[archived.pk]))
        self.assertRedirects(get_response, reverse('courses:semester_list'))
        self.assertErrorMessage(get_response)

        post_response = self.client.post(reverse('courses:semester_update', args=[archived.pk]), data=post_data)
        self.assertRedirects(post_response, reverse('courses:semester_list'))
        self.assertIn(SemesterUpdate.ARCHIVED_SEMESTER_ERROR,
                      [str(message) for message in self.get_message_list(post_response)])

        archived.refresh_from_db()
        self.assertEqual(archived.first_day, datetime.date(2020, 1, 1))
        self.assertEqual(archived.last_day, datetime.date(2020, 6, 1))

    def test_SemesterUpdate_view__archive_race_does_not_modify_archived_semester(self):
        """A semester archived while an edit was open can't be written by that edit.

        The form carries the semester as it was when the page loaded, so saving it would write
        the whole row back, dates and the stale open status alike. The re-read under a row lock
        catches the archive that committed first; here the view is handed that stale instance
        to stand in for the race.
        """
        self.client.force_login(self.test_teacher)
        semester = baker.make(
            Semester, status=Semester.Status.ARCHIVED,
            first_day=datetime.date(2020, 1, 1), last_day=datetime.date(2020, 6, 1),
        )
        # what the view loaded before the archive committed
        stale = Semester.objects.get(pk=semester.pk)
        stale.status = Semester.Status.OPEN
        post_data = {
            'first_day': '2021-10-16',
            'last_day': '2021-12-16',
            **generate_formset_data(ExcludedDateFormset, quantity=0)
        }

        with patch.object(SemesterUpdate, 'get_object', return_value=stale):
            response = self.client.post(reverse('courses:semester_update', args=[semester.pk]), data=post_data)

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertErrorMessage(response)
        semester.refresh_from_db()
        self.assertTrue(semester.is_archived)
        self.assertEqual(semester.first_day, datetime.date(2020, 1, 1))
        self.assertEqual(semester.last_day, datetime.date(2020, 6, 1))

    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_SemesterUpdate_view__public_schema_is_404(self, mock_connection):
        """The semester views are tenant-only, so a public-schema request gets the
        NonPublicOnlyViewMixin's 404. The archived check has to run after that mixin, or it
        would query a tenant-only table on a schema that doesn't have it."""
        self.client.force_login(self.test_teacher)
        archived = baker.make(Semester, status=Semester.Status.ARCHIVED)

        self.assert404('courses:semester_update', args=[archived.pk])
        self.assert404('courses:semester_delete', args=[archived.pk])

    def test_SemesterList_view__status_column_names_each_lifecycle_stage(self):
        """The status column shows the semester's own lifecycle stage, so a semester being set
        up reads as Upcoming instead of being lumped in with everything that isn't active."""
        self.client.force_login(self.test_teacher)
        baker.make(Semester, status=Semester.Status.UPCOMING)
        baker.make(Semester, status=Semester.Status.ARCHIVED)

        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, '>Upcoming<')
        self.assertContains(response, '>Open<')
        self.assertContains(response, '>Archived<')

    def test_SemesterList_view__open_semester_past_its_last_day_is_flagged(self):
        """An open semester whose last day has passed reads as Open - ended, the nudge to
        archive it and free the students' seats."""
        self.client.force_login(self.test_teacher)
        open_semester = SiteConfig.get().open_semester
        open_semester.last_day = datetime.date.today() - datetime.timedelta(days=1)
        open_semester.save()

        response = self.client.get(reverse('courses:semester_list'))

        self.assertContains(response, '>Open - ended<')

    def test_SemesterList_view__names_the_single_open_semester(self):
        """With one semester running, the heading names it, so staff can see at a glance which
        one their students are in."""
        self.client.force_login(self.test_teacher)
        open_semester = SiteConfig.get().open_semester

        response = self.client.get(reverse('courses:semester_list'))

        self.assertEqual(list(response.context['open_semesters']), [open_semester])
        self.assertContains(response, f'Open semester: {open_semester}')

    def test_SemesterList_view__names_every_open_semester(self):
        """A deck running course groups on different calendars has more than one semester open
        at once (#1781), so the heading lists them all rather than naming only the one the deck
        happens to point at."""
        self.client.force_login(self.test_teacher)
        running = SiteConfig.get().open_semester
        next_term = baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=running.first_day + datetime.timedelta(days=200),
            last_day=running.last_day + datetime.timedelta(days=200),
        )

        response = self.client.get(reverse('courses:semester_list'))

        # newest term first, the order the list itself is in
        self.assertEqual(list(response.context['open_semesters']), [next_term, running])
        self.assertContains(response, 'Open semesters:')
        self.assertContains(response, str(next_term))

    def test_SemesterList_view__says_so_when_nothing_is_open(self):
        """Between semesters the heading says nobody can join or earn XP, instead of leaving a
        blank where the open semester's name would be."""
        self.client.force_login(self.test_teacher)
        semester = SiteConfig.get().active_semester
        semester.status = Semester.Status.ARCHIVED
        semester.save()

        response = self.client.get(reverse('courses:semester_list'))

        self.assertEqual(list(response.context['open_semesters']), [])
        self.assertContains(response, 'No semester is open')

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
            self.assertIn(ed.date, exclude_dates)

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
            self.assertIn(ed.date, updated_exclude_dates)

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
    def test_SemesterArchive__student_with_negative_xp__view(self, xp_per_course):
        """
            Test if SemesterArchive returns a warning when there is a course student with
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

        response = self.client.post(reverse('courses:semester_archive', args=[SiteConfig.get().active_semester.id]))
        self.assertWarningMessage(response)
        self.assertRedirects(response, reverse('courses:semester_list'))
        message = self.get_message_list(response)[0]
        self.assertIn('There are some students with negative XP', str(message))

    def test_SemesterDelete_view__deletes_semester(self):
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

    def test_SemesterDelete_view__active_semester_is_blocked(self):
        """Deleting the active semester redirects with an error message and leaves it in
        place. The delete button is hidden in the template, but the URL used to be
        unguarded and a direct request 500'd on the SiteConfig PROTECT constraint."""
        self.client.force_login(self.test_teacher)
        active_semester = SiteConfig.get().active_semester

        response = self.client.post(reverse('courses:semester_delete', args=[active_semester.pk]))

        self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertErrorMessage(response)
        self.assertTrue(Semester.objects.filter(pk=active_semester.pk).exists())

    def test_SemesterDelete_view__archived_semester_is_blocked(self):
        """An archived semester holds its students' final marks, and nothing points at it once
        the deck moves on, so the view refuses to delete it (GET and POST alike)."""
        self.client.force_login(self.test_teacher)
        archived = baker.make(Semester, status=Semester.Status.ARCHIVED)

        for response in (self.client.get(reverse('courses:semester_delete', args=[archived.pk])),
                         self.client.post(reverse('courses:semester_delete', args=[archived.pk]))):
            self.assertRedirects(response, reverse('courses:semester_list'))
        self.assertTrue(Semester.objects.filter(pk=archived.pk).exists())

    def test_SemesterDelete_view__concurrent_activation_still_blocked(self):
        """If the semester becomes active between dispatch's pre-check and the deletion
        (a concurrent activation request), the PROTECT constraint error from the delete
        itself is caught and turned into the same redirect + error message, not a 500."""
        self.client.force_login(self.test_teacher)
        active_semester = SiteConfig.get().active_semester

        # Simulate the race: the dispatch pre-check sees a different semester as active,
        # while the database still protects the truly active one.
        mock_config = MagicMock()
        mock_config.active_semester = baker.make(Semester)
        with patch('courses.views.SiteConfig.get', return_value=mock_config):
            response = self.client.post(reverse('courses:semester_delete', args=[active_semester.pk]))

        self.assertRedirects(response, reverse('courses:semester_list'), fetch_redirect_response=False)
        self.assertErrorMessage(response)
        self.assertTrue(Semester.objects.filter(pk=active_semester.pk).exists())

    def test_SemesterDelete_view__lists_registrations_in_context(self):
        """The delete confirmation page lists the students registered in the semester."""
        self.client.force_login(self.test_teacher)
        semester = baker.make(Semester)
        registration = baker.make(CourseStudent, user=baker.make(User), course=baker.make(Course), semester=semester)

        response = self.client.get(reverse('courses:semester_delete', args=[semester.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(registration, response.context['registrations'])


class BlockViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher for the class tests."""
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)

    def test_BlockList_view__staff_can_view(self):
        """ Admin should be able to view block list """
        self.client.force_login(self.test_teacher)
        response = self.assert200('courses:block_list')

        # Should contain one block
        self.assertEqual(response.context['object_list'].count(), 1)

    def test_BlockCreate_view__staff_can_create(self):
        """ Admin should be able to create a block """
        self.client.force_login(self.test_teacher)
        data = {
            'name': 'My Block',
        }

        response = self.client.post(reverse('courses:block_create'), data=data)
        self.assertRedirects(response, reverse('courses:block_list'))

        block = Block.objects.get(name=data['name'])
        self.assertEqual(block.name, data['name'])

    def test_BlockUpdate_view__staff_can_update(self):
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

        self.client.force_login(self.test_teacher)

        # register student to block
        course_student = baker.make(CourseStudent, user=student, block=block)
        self.assertEqual(CourseStudent.objects.count(), 1)
        self.assertEqual(CourseStudent.objects.first().pk, course_student.pk)

        # confirm block existence
        self.assertIsNotNone(Block.objects.filter(id=block.pk).first())

        # confirm deletion prevention text shows up
        response = self.client.get(reverse('courses:block_delete', args=[block.pk]))

        dt_ptag = f"Unable to delete '{block.name}' as it still has students registered. Consider disabling the block by toggling the"
        dt_atag_link = reverse('courses:block_update', args=[block.pk])
        dt_well_ptag = f"Registered Students: {block.coursestudent_set.count()}"
        self.assertContains(response, dt_ptag)
        self.assertContains(response, dt_atag_link)
        self.assertContains(response, dt_well_ptag)

    def test_BlockForm__initial_values(self):
        """
            Test if the form passed through context has correct initial values
        """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('courses:block_create'))
        form = response.context['form']

        self.assertEqual(form['current_teacher'].value(), SiteConfig.get().deck_owner.pk)


class TestAjax_MarkDistributionChart(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, block, course and active/inactive semesters for the chart tests."""
        cls.teacher = baker.make(User, is_staff=True)

        cls.block = baker.make(Block)
        cls.course = baker.make(Course)
        cls.semester = SiteConfig.get().active_semester
        cls.inactive_semester = baker.make(Semester)

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

    def test_get_student_mark_list__query_count_flat_as_students_grow(self):
        """get_student_mark_list select_relates each student's profile, so its
        query count does not grow with the number of students (it reads
        student.profile.mark_cached for every student)."""
        self.create_student_course(50)
        self.create_student_course(60)
        # warm SiteConfig/content-type caches so only the student marks matter
        self.semester.get_student_mark_list(students_only=True)

        with CaptureQueriesContext(connection) as few_queries:
            self.semester.get_student_mark_list(students_only=True)

        for _ in range(4):
            self.create_student_course(70)

        with CaptureQueriesContext(connection) as many_queries:
            self.semester.get_student_mark_list(students_only=True)

        # without select_related('profile') each extra student adds a query
        self.assertEqual(len(many_queries.captured_queries), len(few_queries.captured_queries))

    def test_non_ajax_status_code__forbidden(self):
        """A non-ajax request to the mark distribution chart is forbidden (403)."""
        self.assert403('courses:mark_distribution_chart', args=[self.teacher.pk])

    def test_ajax_status_code__anonymous_redirected(self):
        """An anonymous ajax request to the mark distribution chart is sent to the login page."""
        # an ajax request clears the 403 the non-ajax test covers, so this reaches LoginRequiredMixin
        url = reverse('courses:mark_distribution_chart', args=[self.teacher.pk])
        self.assertLoginRedirect(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)

    def test_ajax_status_code__students(self):
        """A logged-in student's ajax request to the mark distribution chart succeeds (200)."""
        user = baker.make(User)
        self.client.force_login(user)

        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    def test_ajax_status_code__teachers(self):
        """A logged-in teacher's ajax request to the mark distribution chart succeeds (200)."""
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('courses:mark_distribution_chart', args=[self.teacher.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    def test_histogram_values__exclude_users_outside_active_semester(self):
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

    def test_histogram_values__compare_against_the_students_own_semester(self):
        """A student is charted against their own classmates rather than every current
        student on the deck (issue #2157 Phase 3), so two cohorts on different calendars
        each see their own distribution."""
        other_semester = baker.make(Semester, status=Semester.Status.OPEN)
        [self.create_student_course(100) for _ in range(7)]  # the deck's other cohort
        cohort = [self.create_student_course(100) for _ in range(3)]
        for course_student in cohort:
            course_student.semester = other_semester
            course_student.save()

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('courses:mark_distribution_chart', args=[cohort[0].user.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        json_response = json.loads(response.content)
        # their 2 classmates plus their own bar, which is added back into this histogram.
        # Charting against the whole deck instead would add the other cohort's 7 as well.
        self.assertEqual(sum(json_response['data']['students']), len(cohort))

    def test_histogram_values__unmarked_classmate_does_not_break_the_chart(self):
        """A classmate who has never had a mark calculated has mark_cached None, and numpy
        can't clip None against a number, so leaving it in returned a 500 to everyone in
        that semester. Unmarked classmates are left out of the distribution instead."""
        marked = self.create_student_course(100)
        marked.user.profile.mark_cached = 60
        marked.user.profile.save()
        unmarked = self.create_student_course(50)
        unmarked.user.profile.mark_cached = None
        unmarked.user.profile.save()

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('courses:mark_distribution_chart', args=[marked.user.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        # the marked student's own bar; the unmarked classmate contributes nothing
        self.assertEqual(sum(json.loads(response.content)['data']['students']), 1)

    def test_histogram_values__empty_class_between_semesters(self):
        """Between semesters an unregistered viewer has no semester at all to be charted
        against, so there are no classmates rather than a crash on the missing semester."""
        self.create_student_course(100)
        stranger = baker.make(User)
        Semester.objects.complete_semester()

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('courses:mark_distribution_chart', args=[stranger.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        # only the viewer's own bar, which is always added into this histogram
        self.assertEqual(sum(json.loads(response.content)['data']['students']), 1)

    def test_histogram_values__exclude_test_users(self):
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


class TestAjax_TagChart(ByteDeckTenantTestCase):
    """Tests for the Ajax_TagChart view (courses:ajax_tag_progress_chart), which returns
    per-tag quest/badge XP datasets for chart.js."""

    @classmethod
    def setUpTestData(cls):
        """Create the target user whose tag chart is requested, and cache the active semester."""
        cls.user = baker.make(User)
        cls.semester = SiteConfig.get().active_semester

    def _tagged_quest_with_submissions(self, tag, xp, max_xp, quantity):
        """Make a tagged quest and `quantity` approved, active-semester submissions for self.user.

        xp_requested is pinned to 0 so each submission's earned xp is deterministically the
        quest's xp (Greatest(quest.xp, xp_requested)).
        """
        quest = baker.make(Quest, xp=xp, max_xp=max_xp)
        quest.tags.add(tag)
        baker.make(
            QuestSubmission, quest=quest, user=self.user,
            is_completed=True, is_approved=True, do_not_grant_xp=False,
            xp_requested=0, semester=self.semester, _quantity=quantity,
        )
        return quest

    def _tagged_badge_with_assertions(self, tag, xp, quantity):
        """Make a tagged badge and `quantity` active-semester assertions for self.user."""
        badge = baker.make(Badge, xp=xp)
        badge.tags.add(tag)
        baker.make(
            BadgeAssertion, badge=badge, user=self.user,
            do_not_grant_xp=False, semester=self.semester, _quantity=quantity,
        )
        return badge

    def test_non_ajax_status_code__forbidden(self):
        """A non-ajax request to the tag chart is forbidden (403)."""
        self.assert403('courses:ajax_tag_progress_chart', args=[self.user.pk])

    def test_ajax_status_code__anonymous_redirected(self):
        """An anonymous ajax request to the tag chart is sent to the login page."""
        url = reverse('courses:ajax_tag_progress_chart', args=[self.user.pk])
        self.assertLoginRedirect(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)

    def test_ajax__no_tag_data_returns_empty_datasets(self):
        """With no tagged quests/badges, the chart returns 200 with empty quest/badge datasets."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('courses:ajax_tag_progress_chart', args=[self.user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)['data']
        self.assertEqual(data['quest_dataset'], [])
        self.assertEqual(data['badge_dataset'], [])

    def test_ajax__builds_quest_and_badge_datasets(self):
        """The chart builds per-tag datasets from the user's tagged quest submissions and badge assertions.

        The capped quest (max_xp set) with two submissions exercises the max-xp cutoff loop and the
        ordinal-in-name path; the uncapped quest (max_xp = -1) exercises the keep-everything branch;
        the badge with two assertions exercises the badge loop and its ordinal-in-name path.
        """
        self._tagged_quest_with_submissions('alpha', xp=50, max_xp=60, quantity=2)
        self._tagged_quest_with_submissions('beta', xp=20, max_xp=-1, quantity=1)
        self._tagged_badge_with_assertions('alpha', xp=30, quantity=2)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('courses:ajax_tag_progress_chart', args=[self.user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('alpha', payload['labels'])
        quest_names = [d['name'] for d in payload['data']['quest_dataset']]
        badge_names = [d['name'] for d in payload['data']['badge_dataset']]
        # the two-submission quest and two-assertion badge get an ordinal appended to their name
        self.assertTrue(any('(' in name for name in quest_names), quest_names)
        self.assertTrue(any('(' in name for name in badge_names), badge_names)

    def test_ajax__under_cap_keeps_all_and_single_assertion_has_no_ordinal(self):
        """A capped quest whose submissions stay under max_xp keeps every submission (the max-xp
        cutoff loop finishes without breaking), and a badge with a single assertion gets no
        ordinal suffix on its name."""
        # xp 10 x2 = 20, well under max_xp 100, so the cutoff loop never breaks
        quest = self._tagged_quest_with_submissions('gamma', xp=10, max_xp=100, quantity=2)
        # a single assertion -> count() == 1 -> no "(ordinal)" appended
        self._tagged_badge_with_assertions('gamma', xp=15, quantity=1)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('courses:ajax_tag_progress_chart', args=[self.user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        quest_names = [d['name'] for d in payload['data']['quest_dataset']]
        badge_names = [d['name'] for d in payload['data']['badge_dataset']]
        # both under-cap submissions are kept (the cutoff loop never dropped one)
        self.assertEqual(
            sum(name == quest.name or name.startswith(f'{quest.name} (') for name in quest_names),
            2,
        )
        self.assertTrue(badge_names)
        self.assertTrue(all('(' not in name for name in badge_names), badge_names)


class TestAjax_ProgressChart(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student registered in a course with a fixed-date active semester for the progress chart tests."""
        cls.student = baker.make(User)
        cls.block = baker.make(Block)
        cls.course = baker.make(Course)

        # freeze_time doesnt affect "SiteConfig.get().active_semester"
        # we have to manually set the dates
        cls.semester = SiteConfig.get().active_semester
        cls.semester.first_day = datetime.date(2024, 1, 1)  # keep in mind this is in localtime
        cls.semester.last_day = cls.semester.first_day + datetime.timedelta(days=135)
        cls.semester.save()

        cls.student_course = baker.make(
            CourseStudent,
            user=cls.student,
            semester=cls.semester,
            course=cls.course,
            block=cls.block
        )

        # use this to make aware datetime objects
        # (UTC-8) for datetime.date(2024, 1, 1)
        cls.tz = timezone.get_default_timezone()
        cls.base_xp = 1

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

    def test_non_ajax_status_code__forbidden(self):
        """ 403 unless verified ajax POST request """
        self.assert403('courses:ajax_progress_chart', args=[self.student.pk])

    def test_ajax_status_code__anonymous_redirected(self):
        """An anonymous ajax request to the progress chart is sent to the login page, POST or GET."""
        url = reverse('courses:ajax_progress_chart', args=[self.student.pk])

        self.assertLoginRedirect(self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)
        self.assertLoginRedirect(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)

    def test_ajax_status_code__student(self):
        """A student's ajax POST to the progress chart succeeds (200) while a GET returns 404."""
        self.client.force_login(self.student)

        # post
        response = self.client.post(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

        # get
        response = self.client.get(reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 404)

    def test_ajax_status_code__user_id_zero_uses_request_user(self):
        """user_id=0 resolves to the logged-in user (request.user), so a student's own POST succeeds (200)."""
        self.client.force_login(self.student)
        response = self.client.post(reverse('courses:ajax_progress_chart', args=[0]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

    @freeze_time('2024-01-06')  # a Saturday
    def test_ajax_xp_data__empty_for_a_semester_with_no_class_days_yet(self):
        """A semester with no dates set has no class days behind it, so there are no points to
        plot. The weekend adjustment reads the last point, so an empty chart has to short
        circuit before it rather than raising IndexError."""
        self.semester.first_day = None
        self.semester.last_day = None
        self.semester.save()
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'days_in_semester': 0, 'xp_data': []})

    def test_ajax_xp_data__empty_with_no_open_semester(self):
        """Between semesters there is no semester to chart progress through, so the chart gets
        an empty dataset instead of the page failing."""
        Semester.objects.complete_semester()
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:ajax_progress_chart', args=[self.student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'days_in_semester': 0, 'xp_data': []})

    @freeze_time('2024-02-01')
    def test_ajax_progress_chart__charts_the_students_own_semester(self):
        """A deck can run two cohorts on different calendars (#1781), and the chart is drawn over
        the semester's class days. Charting a student against the deck's default semester would
        give the other cohort someone else's term: the wrong length, and the wrong first day to
        count their XP from."""
        their_semester = baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=datetime.date(2024, 1, 15), last_day=datetime.date(2024, 3, 15),
        )
        their_student = baker.make(User)
        baker.make(
            CourseStudent, user=their_student, semester=their_semester,
            course=baker.make(Course), block=baker.make(Block),
        )
        self.client.force_login(their_student)

        response = self.client.post(
            reverse('courses:ajax_progress_chart', args=[their_student.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        data = json.loads(response.content)
        self.assertEqual(data['days_in_semester'], their_semester.num_days())
        self.assertNotEqual(their_semester.num_days(), self.semester.num_days())
        # their term started Jan 15, so only its class days are plotted, not the deck semester's
        self.assertEqual(len(data['xp_data']), their_semester.days_so_far())

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

    def test_ajax_xp_data__weekend_with_nothing_earned_leaves_the_last_day_alone(self):
        """A weekend where the student earned nothing leaves the last plotted day's total as it was.

        The weekend branch rolls XP earned on a Saturday or Sunday back onto the last class day,
        because work done then does not get its own point on the chart. This is the other side of
        that: with nothing earned there is nothing to roll back, and the Friday total stands.
        """
        self.client.force_login(self.student)

        # submissions Monday to Friday, and nothing over the weekend that follows
        starting_date = datetime.datetime(2024, 1, 1, tzinfo=self.tz)
        for i in range(5):
            self.create_quest_and_submissions(self.base_xp, starting_date + datetime.timedelta(days=i))
        weekday_xp = self.base_xp * 5

        # 2024-1-6 (Saturday)
        with freeze_time(datetime.datetime(2024, 1, 6, 6, tzinfo=self.tz)):
            self.assertEqual(datetime.datetime.now().weekday(), 5)  # 5 == Saturday
            response = self.client.post(
                reverse('courses:ajax_progress_chart', args=[self.student.pk]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(json.loads(response.content)['xp_data'][-1]['y'], weekday_xp)

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


class MarkCalculationsViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student registered in a course worth 1000 XP for 100% for the mark calculation tests."""
        cls.student = baker.make(User)

        cls.block = baker.make(Block)
        cls.course = baker.make(Course, xp_for_100_percent=1000)

        cls.stu_course = baker.make(
            CourseStudent,
            user=cls.student,
            semester=SiteConfig.get().active_semester,
            block=cls.block,
            course=cls.course,
        )

    def setUp(self):
        """Turn on mark-calculation display so the page is reachable."""
        # to show mark calculation page without 404 you need to turn this on
        # (stays in setUp: SiteConfig writes populate cross-test caches)
        siteconfig = SiteConfig.get()
        siteconfig.display_marks_calculation = True
        siteconfig.save()

    def test_mark_calculations__deactivated_shows_staff_the_deactivated_notice(self):
        """When mark-calculation display is turned off, staff get the 'deactivated' notice page
        (students get a 404 instead, since they shouldn't reach this URL)."""
        siteconfig = SiteConfig.get()
        siteconfig.display_marks_calculation = False
        siteconfig.save()

        self.client.force_login(baker.make(User, is_staff=True))
        response = self.client.get(reverse('courses:my_marks'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'courses/mark_calculations_deactivated.html')

    def test_mark_calculations__staff_can_view_another_students_marks(self):
        """Staff can view a specific student's mark page via the user_id URL."""
        self.client.force_login(baker.make(User, is_staff=True))
        self.assert200('courses:marks', args=[self.student.pk])

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


class AjaxRankPopupTests(ByteDeckTenantTestCase):
    """ test case for
    + ajax/on_show_ranked_popup/
    + ajax/on_close_ranked_popup/
    """

    @classmethod
    def setUpTestData(cls):
        """Create a student for the rank popup tests."""
        cls.student = baker.make(User)

    def test_status_codes__ranked_popup_endpoints(self):
        ''' tests correct status codes for `on_show_ranked_popup` and `on_close_ranked_popup`
        403 - because not ajax
        302 - because of not logged in (LoginRequiredMixin)
        200 - success
        '''

        # test anon
        # ajax_on_show_ranked_popup
        self.assert403('courses:ajax_on_show_ranked_popup')
        url = reverse('courses:ajax_on_show_ranked_popup')
        self.assertLoginRedirect(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)

        # ajax_on_close_ranked_popup
        self.assert403('courses:ajax_on_close_ranked_popup')
        url = reverse('courses:ajax_on_close_ranked_popup')
        self.assertLoginRedirect(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), url)

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

    def test_on_show_ranked_popup__correct_ranks(self):
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

    def test_on_close_ranked_popup__marks_latest_read(self):
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


class DeckCapacityEnforcementTests(ByteDeckTenantTestCase):
    """Enforcement of the deck's current-student cap at the registration choke points
    (#1729 PR 4; closes the 'trial mode (max 5 users)' checkbox of #1730)."""

    def setUp(self):
        """Give the deck a subscribed cap of 1, fill that seat, and log nobody in yet.

        The deck cache is cleared because the cache backend outlives each test's
        transaction.
        """
        from django.core.cache import cache

        from tenant.utils import deck_cache_key

        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.tenant.paid_until = timezone.localdate() + datetime.timedelta(days=30)
        self.tenant.max_active_users = 1
        self.tenant.save()

        self.occupant = baker.make(User)
        baker.make('courses.CourseStudent', user=self.occupant, active=True, semester=SiteConfig.get().active_semester)
        self.newcomer = baker.make(User)
        self.staff = baker.make(User, is_staff=True)

    def test_student_registration__refused_at_cap(self):
        """A student hitting the join page on a full deck sees the student-facing
        refusal instead of the form, on both GET and POST, and no registration happens."""
        self.client.force_login(self.newcomer)

        response = self.client.get(reverse('courses:create'))
        self.assertContains(response, 'reached its limit of current students')

        response = self.client.post(reverse('courses:create'), data={})
        self.assertContains(response, 'reached its limit of current students')
        self.assertFalse(CourseStudent.objects.filter(user=self.newcomer).exists())

    def test_student_registration__allowed_below_cap(self):
        """With a free seat, the join page renders the normal registration form."""
        self.tenant.max_active_users = 2
        self.tenant.save()
        self.client.force_login(self.newcomer)

        response = self.assert200('courses:create')
        self.assertNotContains(response, 'reached its limit of current students')

    def test_student_registration__simplified_auto_create_blocked_at_cap(self):
        """The simplified-registration auto-create shortcut cannot bypass the cap: the
        guard runs before it, so the student sees the refusal and no row is created."""
        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()
        self.client.force_login(self.newcomer)

        response = self.client.get(reverse('courses:create'))
        self.assertContains(response, 'reached its limit of current students')
        self.assertFalse(CourseStudent.objects.filter(user=self.newcomer).exists())

    def test_staff_add_student__refused_at_cap_with_helpful_links(self):
        """Staff adding a student to a full deck see the staff-facing refusal with the
        archive-help and subscription-page links, on both GET and POST."""
        self.client.force_login(self.staff)
        url = reverse('courses:join', args=[self.newcomer.id])

        response = self.client.get(url)
        self.assertContains(response, 'Current-student limit reached')
        self.assertContains(response, reverse('courses:archive_students_help'))
        # PR 6: the upgrade link now goes to the deck's own subscription page
        self.assertContains(response, reverse('decks:subscription'))

        response = self.client.post(url, data={})
        self.assertContains(response, 'Current-student limit reached')
        self.assertFalse(CourseStudent.objects.filter(user=self.newcomer).exists())

    def test_staff_add_student__staff_target_allowed_at_cap(self):
        """Adding a STAFF member to a course is always allowed -- staff never consume seats."""
        other_staff = baker.make(User, is_staff=True)
        self.client.force_login(self.staff)

        response = self.assert200('courses:join', args=[other_staff.id])
        self.assertNotContains(response, 'Current-student limit reached')

    def test_archive_students_help__staff_only(self):
        """The archive-students help page renders for staff and is blocked for students."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse('courses:archive_students_help'))
        self.assertContains(response, 'Freeing up student seats')

        self.client.force_login(self.newcomer)
        self.assert403('courses:archive_students_help')
