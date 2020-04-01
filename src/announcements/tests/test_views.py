# Create your tests here.
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from model_mommy import mommy

# from unittest.mock import patch

from announcements.models import Announcement

User = get_user_model()


class AnnouncementViewTests(TestCase):

    def setUp(self):
        # djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = mommy.make(User)

        # needed because BadgeAssertions use a default that might not exist yet
        # self.sem = mommy.make('courses.semester', pk=djconfig.config.hs_active_semester)

        self.test_announcement = mommy.make(Announcement, draft=False)
        self.ann_pk = self.test_announcement.pk

    def assertRedirectsHome(self, url_name, args=None):
        self.assertRedirects(
            response=self.client.get(reverse(url_name, args=args)),
            expected_url='%s?next=%s' % (reverse('home'), reverse(url_name, args=args)),
        )

    def assertRedirectsAdmin(self, url_name, args=None):
        self.assertRedirects(
            response=self.client.get(reverse(url_name, args=args)),
            expected_url='{}?next={}'.format('/admin/login/', reverse(url_name, args=args)),
        )

    def assert200(self, url_name, args=None):
        self.assertEqual(
            self.client.get(reverse(url_name, args=args)).status_code,
            200
        )

    def test_all_announcement_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page or admin  '''

        # go home
        self.assertRedirectsHome('announcements:list')
        self.assertRedirectsHome('announcements:list2')
        self.assertRedirectsHome('announcements:comment', args=[1])
        self.assertRedirectsHome('announcements:list', args=[1])

        # go admin
        self.assertRedirectsAdmin('announcements:create')
        self.assertRedirectsAdmin('announcements:delete', args=[1])
        self.assertRedirectsAdmin('announcements:update', args=[1])
        self.assertRedirectsAdmin('announcements:copy', args=[1])
        self.assertRedirectsAdmin('announcements:publish', args=[1])

    def test_all_announcement_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # all_fields = self.test_announcement._meta.get_fields()
        # for field in all_fields:
        #     print(field, getattr(self.test_announcement, field.name))

        # students should have access to these:
        self.assertEqual(self.client.get(reverse('announcements:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('announcements:list2')).status_code, 200)
        self.assertEqual(self.client.get(reverse('announcements:list', args=[self.ann_pk])).status_code, 200)

        # Announcement from setup() should appear in the list
        self.assertContains(self.client.get(reverse('announcements:list')), self.test_announcement.title)

        comment_response_get = self.client.get(reverse('announcements:comment', args=[self.ann_pk]))
        self.assertEqual(comment_response_get.status_code, 404)  # Comments via POST only

        # Posting a comment redirects to the announcement commented on
        self.assertRedirects(
            response=self.client.post(reverse('announcements:comment', args=[self.ann_pk])),
            expected_url=reverse('announcements:list', args=[self.ann_pk]),
        )

        # These views should redirect to admin login
        self.assertRedirectsAdmin('announcements:create')
        self.assertRedirectsAdmin('announcements:delete', args=[1])
        self.assertRedirectsAdmin('announcements:update', args=[1])
        self.assertRedirectsAdmin('announcements:copy', args=[1])
        self.assertRedirectsAdmin('announcements:publish', args=[1])

    def test_all_announcement_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        self.assertEqual(self.client.get(reverse('announcements:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('announcements:list2')).status_code, 200)
        self.assertEqual(self.client.get(reverse('announcements:list', args=[self.ann_pk])).status_code, 200)

        # Announcement from setup() should appear in the list
        self.assertContains(self.client.get(reverse('announcements:list')), self.test_announcement.title)

        comment_response_get = self.client.get(reverse('announcements:comment', args=[self.ann_pk]))
        self.assertEqual(comment_response_get.status_code, 404)  # Comments via POST only

        # Posting a comment redirects to the announcement commented on
        self.assertRedirects(
            response=self.client.post(reverse('announcements:comment', args=[self.ann_pk])),
            expected_url=reverse('announcements:list', args=[self.ann_pk]),
        )

        # These staff views should work
        self.assert200('announcements:create')
        self.assert200('announcements:update', args=[self.ann_pk])
        self.assert200('announcements:copy', args=[self.ann_pk])
        self.assert200('announcements:delete', args=[self.ann_pk])

        self.assertRedirects(
            response=self.client.post(reverse('announcements:publish', args=[self.ann_pk])),
            expected_url=reverse('announcements:list', args=[self.ann_pk]),
        )

    def test_draft_announcement(self):
        draft_announcement = mommy.make(Announcement)  # default is draft
        self.assertTrue(draft_announcement.draft)

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # Students shoudn't see draft announcements in the list
        self.assertNotContains(self.client.get(reverse('announcements:list')), draft_announcement.title)

        # set draft to false
        draft_announcement.draft = False
        draft_announcement.save()

        # Student can now see it
        self.assertContains(self.client.get(reverse('announcements:list')), draft_announcement.title)

    # @patch('announcements.views.publish_announcement.apply_async')
    def test_publish_announcement(self):
        draft_announcement = mommy.make(Announcement)

        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # draft announcement should appear with a link to publish it.  TODO This is crude, should be checking HTML?
        publish_link = reverse('announcements:publish', args=[draft_announcement.pk])
        self.assertContains(self.client.get(reverse('announcements:list')), publish_link)

        # publish the announcement
        self.assertRedirects(
            response=self.client.post(reverse('announcements:publish', args=[draft_announcement.pk])),
            expected_url=reverse('announcements:list', args=[draft_announcement.pk]),
        )

        # Should probably mock the task in above code, but don't know how...
        # Fake mock...?
        draft_announcement.draft = False
        draft_announcement.save()

        # publish link for this announcement should no longer appear in the list:
        self.assertNotContains(self.client.get(reverse('announcements:list')), publish_link)
