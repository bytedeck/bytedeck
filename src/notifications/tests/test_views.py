# Create your tests here.
import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy

from notifications.models import Notification


class NotificationViewTests(TestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = mommy.make(User)

        self.test_notification = mommy.make(Notification)

#
#     def test_all_badge_page_status_codes_for_anonymous(self):
#         ''' If not logged in then all views should redirect to home page  '''
#
#         self.assertRedirects(
#             response=self.client.get(reverse('badges:list')),
#             expected_url='%s?next=%s' % (reverse('home'), reverse('badges:list')),
#         )
#
#         # for path in urlpatterns:
#         #     name = 'badges:%s' % path.name
#         #     # path.name
#         #     # print(url)
#         #     self.assertRedirects(
#         #         response=self.client.get(reverse(name)),
#         #         expected_url='%s?next=%s' % (reverse('home'), reverse(name)),
#         #         msg_prefix=name,
#         #     )
#
#     def test_all_badge_page_status_codes_for_students(self):
#
#         # log in a student
#         success = self.client.login(username=self.test_student1.username, password=self.test_password)
#         self.assertTrue(success)
#
#         b_pk = self.test_badge.pk
#         a_pk = self.test_assertion.pk
#         s_pk = self.test_student1.pk
#
#         self.assertEqual(self.client.get(reverse('badges:list')).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_detail', args=[b_pk])).status_code, 200)
#
#         # students shouldn't have access to these and should be redirected
#         self.assertEqual(self.client.get(reverse('badges:badge_create')).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:badge_update', args=[b_pk])).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:badge_copy', args=[b_pk])).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:badge_delete', args=[b_pk])).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:grant', args=[b_pk, s_pk])).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:bulk_grant_badge', args=[b_pk])).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:bulk_grant')).status_code, 302)
#         self.assertEqual(self.client.get(reverse('badges:revoke', args=[s_pk])).status_code, 302)
#
#     def test_all_badge_page_status_codes_for_teachers(self):
#         # log in a teacher
#         success = self.client.login(username=self.test_teacher.username, password=self.test_password)
#         self.assertTrue(success)
#
#         b_pk = self.test_badge.pk
#         a_pk = self.test_assertion.pk
#         s_pk = self.test_student1.pk
#
#         self.assertEqual(self.client.get(reverse('badges:list')).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_detail', args=[b_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_create')).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_update', args=[b_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_copy', args=[b_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:badge_delete', args=[b_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:grant', args=[b_pk, s_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:bulk_grant_badge', args=[b_pk])).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:bulk_grant')).status_code, 200)
#         self.assertEqual(self.client.get(reverse('badges:revoke', args=[a_pk])).status_code, 200)
#
#
# # class ViewTests(TestCase):
#
#
#     # def test_view_url_by_name(self):
#     #     response = self.client.get(reverse('home'))
#     #     self.assertEqual(response.status_code, 200)
#     #
#     # def test_view_uses_correct_template(self):
#     #     response = self.client.get(reverse('home'))
#     #     self.assertEqual(response.status_code, 200)
#     #     self.assertTemplateUsed(response, 'home.html')
#     #
#     # def test_home_page_contains_correct_html(self):
#     #     response = self.client.get('/')
#     #     self.assertContains(response, '<h1>Homepage</h1>')
#     #
#     # def test_home_page_does_not_contain_incorrect_html(self):
#     #     response = self.client.get('/')
#     #     self.assertNotContains(
#     #         response, 'Hi there! I should not be on the page.')
