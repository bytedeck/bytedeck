from datetime import timedelta

from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from announcements.forms import AnnouncementForm
from announcements.models import Announcement
from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class AnnouncementViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.client = TenantClient(self.tenant)

        self.test_password = "password"
        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        self.test_announcement = baker.make(Announcement, draft=False)
        self.ann_pk = self.test_announcement.pk

    def test_all_announcement_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page or admin  '''

        # go home
        self.assertRedirectsLogin('announcements:list')
        self.assertRedirectsLogin('announcements:list2')
        self.assertRedirectsLogin('announcements:comment', args=[1])
        self.assertRedirectsLogin('announcements:list', args=[1])

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

        self.assert200('announcements:list')
        self.assert200('announcements:list2')
        self.assert200('announcements:list', args=[self.ann_pk])

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
        draft_announcement = baker.make(Announcement)  # default is draft
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

    def test_archived_announcement(self):
        """ Archived announcements should not appear in announcements list"""
        archived_announcement = baker.make(Announcement, archived=True)
        self.assertTrue(archived_announcement.archived)

        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # Users shouldn't see archived announcements in the list
        self.assertNotContains(self.client.get(reverse('announcements:list')), archived_announcement.title)

        # set archived to False
        archived_announcement.archived = False
        archived_announcement.save()

        # Users can now see it
        self.assertContains(self.client.get(reverse('announcements:list')), archived_announcement.title)

    def test_announcements_archived_after_semester_close(self):
        """ All unarchived announcements should be archived when a semester is closed """

        announcements = [baker.make(Announcement, archived=False) for _ in range(5)]

        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        self.client.get(reverse('courses:end_active_semester'))

        for announcement in announcements:
            announcement.refresh_from_db()
            self.assertTrue(announcement.archived)

    # @patch('announcements.views.publish_announcement.apply_async')
    def test_publish_announcement(self):
        draft_announcement = baker.make(Announcement)

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

    def test_create_announcement_from_past_date_auto_publish(self):
        draft_announcement = baker.make(
            Announcement,
            datetime_released=timezone.now() - timedelta(days=3),
            auto_publish=True,
        )
        form = AnnouncementForm(data=model_to_dict(draft_announcement))
        self.assertFalse(form.is_valid())

    def test_comment_on_announcement_by_student(self):
        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        form_data = {
            'comment_text': "test comment",
        }
        response = self.client.post(reverse('announcements:comment', args=[self.test_announcement.id]), form_data)
        self.assertEqual(response.status_code, 404)  # invalid submit button

        # make sure it was submitted with the 'comment_button'
        form_data['comment_button'] = True
        response = self.client.post(
            reverse('announcements:comment', args=[self.test_announcement.id]),
            data=form_data
        )

        # Empty comment strings should be replaced with blank string or we get an error
        # WHY? THIS SEEMS SILLY! THE FORM SHOULDN'T VALIDATE IF THERE IS NO COMMENT!
        # Old code not relevant any more?
        # form_data['comment_text'] = None
        # response = self.client.post(
        #     reverse('announcements:comment', args=[self.test_announcement.id]),
        #     data=form_data
        # )
        # self.assertRedirects(response, self.test_announcement.get_absolute_url())

    def test_copy_announcement(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # hit the view as a get request first, to load a copy of the announcement in the form
        response = self.client.get(
            reverse('announcements:copy', args=[self.test_announcement.id]),
        )
        self.assertEqual(response.status_code, 200)

        # Don't know how to get the form data from the get request...
        # https://stackoverflow.com/questions/61532873/how-to-plug-the-reponse-of-a-django-view-get-request-into-the-same-view-as-a-pos

        # So, instead we'll manually create valid form data for post request:
        form_data = {
            'title': "Copy test",
            'content': "test content",
            'datetime_released': "2006-10-25 14:30:59"  # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-DATETIME_INPUT_FORMATS
        }

        response = self.client.post(
            reverse('announcements:copy', args=[self.test_announcement.id]),
            data=form_data
        )

        # Get the newest announcement
        new_ann = Announcement.objects.latest('datetime_created')
        self.assertEqual(new_ann.title, "Copy test")
        # if successful, should redirect to the new announcement
        self.assertRedirects(
            response,
            new_ann.get_absolute_url()
        )
