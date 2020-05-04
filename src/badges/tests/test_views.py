from django.contrib.auth import get_user_model
from django.urls import reverse
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

from siteconfig.models import SiteConfig
from badges.models import BadgeAssertion, Badge


class ViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        # needed because BadgeAssertions use a default that might not exist yet
        self.sem = SiteConfig.get().active_semester

        self.test_badge = baker.make(Badge)
        self.test_assertion = baker.make(BadgeAssertion)

    def test_all_badge_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home or admin page  '''
        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assertRedirectsHome('badges:list')
        self.assertRedirectsHome('badges:badge_detail', args=[b_pk])
        self.assertRedirectsHome('badges:badge_create')
        self.assertRedirectsAdmin('badges:badge_update', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_copy', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_delete', args=[b_pk])
        self.assertRedirectsAdmin('badges:grant', args=[b_pk, s_pk])
        self.assertRedirectsAdmin('badges:bulk_grant_badge', args=[b_pk])
        self.assertRedirectsAdmin('badges:bulk_grant')
        self.assertRedirectsAdmin('badges:revoke', args=[a_pk])

    def test_all_badge_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        # a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assert200('badges:list')
        self.assert200('badges:badge_detail', args=[b_pk])

        # students shouldn't have access to these and should be redirected
        self.assertEqual(self.client.get(reverse('badges:badge_create')).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:badge_update', args=[b_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:badge_copy', args=[b_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:badge_delete', args=[b_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:grant', args=[b_pk, s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:bulk_grant_badge', args=[b_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:bulk_grant')).status_code, 302)
        self.assertEqual(self.client.get(reverse('badges:revoke', args=[s_pk])).status_code, 302)

    def test_all_badge_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assert200('badges:list')
        self.assert200('badges:badge_detail', args=[b_pk])
        self.assert200('badges:badge_create')
        self.assert200('badges:badge_update', args=[b_pk])
        self.assert200('badges:badge_copy', args=[b_pk])
        self.assert200('badges:badge_delete', args=[b_pk])
        self.assert200('badges:grant', args=[b_pk, s_pk])
        self.assert200('badges:bulk_grant_badge', args=[b_pk])
        self.assert200('badges:bulk_grant')
        self.assert200('badges:revoke', args=[a_pk])
