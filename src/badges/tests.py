# Create your tests here.
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from djconfig.utils import override_djconfig

from badges.models import BadgeAssertion, Badge


@override_djconfig(hs_active_semester="1")
class BadgeViewTests(TestCase):

    # includes some basic model data
    fixtures = ['initial_data.json']

    def setUp(self):
        User = get_user_model()
        self.test_password = 'password'
        # need a teacher before students can be created or the profile creationwill fail......why?
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = User.objects.create_user('test_student2', password=self.test_password)

        self.test_badge = Badge.objects.get(pk=1)  # create by fixture

        self.test_assertion = BadgeAssertion.objects.create_assertion(user=self.test_student1,
                                                                      badge=self.test_badge,
                                                                      issued_by=self.test_teacher)

    def test_all_badge_page_status_codes_for_anonymous(self):
        # If not logged in then should redirect to home page
        self.assertEquals(self.client.get(reverse('badges:list')).status_code, 302)

    def test_all_badge_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assertEquals(self.client.get(reverse('badges:list')).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_detail', args=[b_pk])).status_code, 200)

        # students shouldn't have access to these and should be redirected
        self.assertEquals(self.client.get(reverse('badges:badge_create')).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:badge_update', args=[b_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:badge_copy', args=[b_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:badge_delete', args=[b_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:grant', args=[b_pk, s_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:bulk_grant_badge', args=[b_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:bulk_grant')).status_code, 302)
        self.assertEquals(self.client.get(reverse('badges:revoke', args=[s_pk])).status_code, 302)

    def test_all_badge_page_status_codes_for_students(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assertEquals(self.client.get(reverse('badges:list')).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_detail', args=[b_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_create')).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_update', args=[b_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_copy', args=[b_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:badge_delete', args=[b_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:grant', args=[b_pk, s_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:bulk_grant_badge', args=[b_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:bulk_grant')).status_code, 200)
        self.assertEquals(self.client.get(reverse('badges:revoke', args=[a_pk])).status_code, 200)


    # def test_view_url_by_name(self):
    #     response = self.client.get(reverse('home'))
    #     self.assertEquals(response.status_code, 200)
    #
    # def test_view_uses_correct_template(self):
    #     response = self.client.get(reverse('home'))
    #     self.assertEquals(response.status_code, 200)
    #     self.assertTemplateUsed(response, 'home.html')
    #
    # def test_home_page_contains_correct_html(self):
    #     response = self.client.get('/')
    #     self.assertContains(response, '<h1>Homepage</h1>')
    #
    # def test_home_page_does_not_contain_incorrect_html(self):
    #     response = self.client.get('/')
    #     self.assertNotContains(
    #         response, 'Hi there! I should not be on the page.')