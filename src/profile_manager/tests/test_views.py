from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from siteconfig.models import SiteConfig


class ProfileViewTests(TenantTestCase):

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

        self.assertRedirects(
            response=self.client.get(reverse('profiles:profile_list')),
            expected_url='%s?next=%s' % (reverse('home'), reverse('profiles:profile_list')),
        )

    def test_all_profile_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        s2_pk = self.test_student2.profile.pk

        # self.assertEqual(self.client.get(reverse('profiles:profile_detail')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_detail', args=[s_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_update', args=[s_pk])).status_code, 200)

        self.assertEqual(self.client.get(reverse('profiles:profile_list_current')).status_code, 200)

        # students shouldn't have access to these and should be redirected to login or permission denied
        self.assertEqual(self.client.get(reverse('profiles:profile_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('profiles:profile_detail', args=[s2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:GameLab_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

        self.assertEqual(self.client.get(reverse('profiles:profile_update', args=[s2_pk])).status_code, 404)

    def test_all_profile_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        # s2_pk = self.test_student2.pk

        self.assertEqual(self.client.get(reverse('profiles:profile_detail', args=[s_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_update', args=[s_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_list_current')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:GameLab_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_profile_recalculate_xp_status_codes(self):
        """Need to test this view with students in an active course"""
        # why testing this here?
        self.assertEqual(self.active_sem.pk, SiteConfig.get().active_semester.pk)

        self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)
