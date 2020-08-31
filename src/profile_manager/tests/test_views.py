from django.contrib.auth import get_user_model
from django.urls import reverse
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig


class ProfileViewTests(ViewTestUtilsMixin, TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        # create semester with pk of default semester
        # this seems backward, but no semesters should exist yet in the test, so their shouldn't be any conflicts.
        self.active_sem = SiteConfig.get().active_semester

    def test_all_profile_page_status_codes_for_anonymous(self):
        """ If not logged in then all views should redirect to home page  """

        self.assertRedirectsLogin('profiles:profile_list')

    def test_all_profile_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        s2_pk = self.test_student2.profile.pk

        self.assert200('profiles:profile_detail', args=[s_pk])
        self.assert200('profiles:profile_update', args=[s_pk])

        self.assert200('profiles:profile_list_current')

        # students shouldn't have access to these and should be redirected to login or permission denied
        self.assert403('profiles:profile_list')

        # viewing the profile of another student
        self.assertRedirectsQuests('profiles:profile_detail', args=[s2_pk])

        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:xp_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

        self.assert404('profiles:profile_update', args=[s2_pk])

    def test_all_profile_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        # s2_pk = self.test_student2.pk

        self.assert200('profiles:profile_detail', args=[s_pk])
        self.assert200('profiles:profile_update', args=[s_pk])
        self.assert200('profiles:profile_list')
        self.assert200('profiles:profile_list_current')
        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:xp_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_profile_recalculate_xp_status_codes(self):
        """Need to test this view with students in an active course"""
        # why testing this here?
        self.assertEqual(self.active_sem.pk, SiteConfig.get().active_semester.pk)

        self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_student_marks_button(self):
        """
        Student should be able to see marks button when `display_marks_calculation` is True.
        Otherwise, they should not be able to see it.
        """

        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # View profile page
        s_pk = self.test_student1.profile.pk

        # `display_marks_calculation` is disabled by default. Student should not be able to view it
        response = self.client.get(reverse('profiles:profile_detail', args=[s_pk]))
        self.assertNotContains(response, 'View your Mark Calculations')

        config = SiteConfig.get()
        config.display_marks_calculation = True
        config.save()

        # Student should be able to view marks calculation
        response = self.client.get(reverse('profiles:profile_detail', args=[s_pk]))
        self.assertContains(response, 'View your Mark Calculations')

    def test_student_view_marks_404_if_disabled(self):
        """
        Student marks should return 404 if disabled by admin.
        """

        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.assert404('courses:my_marks')
