from datetime import timedelta

from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils import timezone

from django_tenants.test.client import TenantClient
from model_bakery import baker

from announcements.forms import AnnouncementForm
from announcements.models import Announcement
from comments.models import Comment
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class AnnouncementViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, students, and a published announcement shared across the test methods."""
        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student1 = User.objects.create_user('test_student')
        cls.test_student2 = baker.make(User)

        cls.test_announcement = baker.make(Announcement, draft=False)
        cls.ann_pk = cls.test_announcement.pk

    def setUp(self):
        """Set up a tenant test client for each test."""
        self.client = TenantClient(self.tenant)

    def test_all_announcement_page_status_codes__anonymous(self):
        ''' If not logged in then all views should redirect to login page '''

        self.assertRedirectsLogin('announcements:list')
        self.assertRedirectsLogin('announcements:archived')
        self.assertRedirectsLogin('announcements:comment', args=[1])
        self.assertRedirectsLogin('announcements:list', args=[1])

        self.assertRedirectsLogin('announcements:create')
        self.assertRedirectsLogin('announcements:delete', args=[1])
        self.assertRedirectsLogin('announcements:update', args=[1])
        self.assertRedirectsLogin('announcements:copy', args=[1])
        self.assertRedirectsLogin('announcements:publish', args=[1])

    def test_all_announcement_page_status_codes__students(self):
        """Students can view lists/comments but get 403 on staff-only announcement views."""
        # log in a student
        self.client.force_login(self.test_student1)

        # students should have access to these:
        self.assert200('announcements:list')
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

        # Authenticated users that aren't staff should get permission denied 403
        self.assert403('announcements:create')
        self.assert403('announcements:delete', args=[1])
        self.assert403('announcements:update', args=[1])
        self.assert403('announcements:copy', args=[1])
        self.assert403('announcements:publish', args=[1])
        self.assert403('announcements:archived')

    def test_all_announcement_page_status_codes__teachers(self):
        """Teachers can access the list, archive, comment, and all staff-only announcement views."""
        # log in a teacher
        self.client.force_login(self.test_teacher)

        self.assert200('announcements:list')
        self.assert200('announcements:archived')
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

    def test_archive_button__visible_to_teachers(self):
        """Teachers see the 'Archived' button on the announcements list."""
        self.client.force_login(self.test_teacher)
        self.assertContains(self.client.get(reverse('announcements:list')), "Archived")

    def test_archive_button__hidden_from_students(self):
        """Students do not see the 'Archived' button on the announcements list."""
        self.client.force_login(self.test_student1)
        self.assertNotContains(self.client.get(reverse('announcements:list')), "Archived")

    def test_draft_announcement__hidden_from_students_until_published(self):
        """Students only see an announcement in the list once it is no longer a draft."""
        draft_announcement = baker.make(Announcement)  # default is draft
        self.assertTrue(draft_announcement.draft)

        # log in a student
        self.client.force_login(self.test_student1)

        # Students shoudn't see draft announcements in the list
        self.assertNotContains(self.client.get(reverse('announcements:list')), draft_announcement.title)

        # set draft to false
        draft_announcement.draft = False
        draft_announcement.save()

        # Student can now see it
        self.assertContains(self.client.get(reverse('announcements:list')), draft_announcement.title)

    # @patch('announcements.views.publish_announcement.apply_async')
    def test_publish_announcement__removes_publish_link(self):
        """Posting to the publish view redirects to the announcement and the publish link disappears once published."""
        draft_announcement = baker.make(Announcement)

        # log in a teacher
        self.client.force_login(self.test_teacher)

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

    def test_create_announcement__past_date_auto_publish_invalid(self):
        """The form rejects an auto-published announcement with a past release date."""
        draft_announcement = baker.make(
            Announcement,
            datetime_released=timezone.now() - timedelta(days=3),
            auto_publish=True,
        )
        form = AnnouncementForm(data=model_to_dict(draft_announcement))
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['datetime_released'], ['An Announcement that is auto published cannot have a past release date.'])

    def test_create_announcement__auto_publish_and_archived_invalid(self):
        """The form rejects an announcement that is both archived and auto-published."""
        draft_announcement = baker.make(
            Announcement,
            datetime_released=timezone.now() - timedelta(days=3),
            auto_publish=True,
        )

        form_data = model_to_dict(draft_announcement)
        form_data['archived'] = True

        form = AnnouncementForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['auto_publish'], ['An Announcement that is archived cannot be auto published.'])
        # self.add_error("auto_publish", forms.ValidationError('An Announcement that is archived cannot be auto published.'))

    def test_comment_on_announcement__by_student(self):
        """A student's comment post requires the comment_button, returning 404 without it."""
        # log in a student
        self.client.force_login(self.test_student1)

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

    def test_comment_on_announcement__escapes_html(self):
        """HTML entered in the announcement comment form is completely escaped when
        the comment is saved, so scripts can't execute when the comment is rendered.
        Regression test for issue #1343.
        """
        self.client.force_login(self.test_student1)

        payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
        response = self.client.post(
            reverse('announcements:comment', args=[self.test_announcement.id]),
            data={'comment_text': payload, 'comment_button': True}
        )
        self.assertRedirects(response, self.test_announcement.get_absolute_url())

        comment = Comment.objects.all_with_target_object(self.test_announcement).first()
        self.assertIsNotNone(comment)
        self.assertNotIn('<script', comment.text)
        self.assertNotIn('<img', comment.text)
        self.assertIn('&lt;script&gt;', comment.text)

    def test_copy_announcement__creates_new_announcement(self):
        """Copying an announcement via POST creates a new announcement and redirects to it."""
        # log in a teacher
        self.client.force_login(self.test_teacher)

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

    # Custom label tests
    def test_announcement_views__header_custom_label_displayed(self):
        """
        Annnouncement Create, Copy, and Edit view headers should change 'announcement' to label set at custom_name_for_announcement model
        field in Siteconfig
        """
        # Login a teacher
        self.client.force_login(self.test_teacher)

        # Change custom_name_for_announcement to a non-default option
        config = SiteConfig.get()
        config.custom_name_for_announcement = "CustomAnnouncement"
        config.save()

        # Get Create view and assert header is correct
        request = self.client.get(reverse('announcements:create'))
        self.assertContains(request, "Create New CustomAnnouncement")
        # Get Copy view and assert header is correct
        request = self.client.get(reverse('announcements:copy', args=[self.test_announcement.id]))
        self.assertContains(request, "Copy another CustomAnnouncement")
        # Get Edit view and assert header is correct
        request = self.client.get(reverse('announcements:update', args=[self.test_announcement.id]))
        self.assertContains(request, 'Edit CustomAnnouncement')
        # Get Delete view and assert header is correct
        request = self.client.get(reverse('announcements:delete', args=[self.test_announcement.id]))
        self.assertContains(request, 'Delete CustomAnnouncement')

    def test_comment_on_announcement__success_message_custom_label_displayed(self):
        """
        Commenting on an announcement should display a success message upon redirect that contains the label set at custom_name_for_announcement
        model field in SiteConfig

        i.e if custom_name_for_announcement = "CustomAnnouncement" success message will display as:
        "CustomAnnouncement commented on"
        """
        # Login a teacher (could be a student, won't affect results but we need a logged-in user)
        self.client.force_login(self.test_teacher)

        # Change custom_name_for_announcement to a non-default option
        config = SiteConfig.get()
        config.custom_name_for_announcement = "CustomAnnouncement"
        config.save()

        # set form data for test comment (comment itself isn't being tested, we just need to make one successfully to redirect with success message)
        form_data = {
            'comment_text': "test comment",
            'comment_button': True,
        }

        # make the comment and follow redirect to list view, with success message displayed (follow=True)
        response = self.client.post(
            reverse('announcements:comment', args=[self.test_announcement.id]),
            data=form_data, follow=True
        )

        # assert the custom label (and the success message) are displayed
        self.assertContains(response, "CustomAnnouncement commented on")


class AnnouncementArchivedViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):
    """ Tests for archived announcements view and other archived processes

    Mostly this one:
    def list(request, ann_id=None, template='announcements/list.html'):
        archived = '/archived/' in request.path_info
    """

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, student, and a published announcement shared across the test methods."""
        cls.test_teacher = baker.make(User, is_staff=True)
        cls.test_student = baker.make(User)
        cls.test_announcement = baker.make(Announcement, draft=False)

    def setUp(self):
        """Set up a tenant test client for each test."""
        self.client = TenantClient(self.tenant)

    def test_archived_announcement__hidden_from_list(self):
        """ Archived announcements should not appear in announcements list"""
        archived_announcement = baker.make(Announcement, archived=True)
        self.assertTrue(archived_announcement.archived)

        self.client.force_login(self.test_teacher)

        # Users shouldn't see archived announcements in the list
        self.assertNotContains(self.client.get(reverse('announcements:list')), archived_announcement.title)

        # set archived to False
        archived_announcement.archived = False
        archived_announcement.save()

        # Users can now see it
        self.assertContains(self.client.get(reverse('announcements:list')), archived_announcement.title)

    def test_archived_announcements__visible_on_archived_page(self):
        """Archived announcements appear on the dedicated archived page."""
        self.client.force_login(self.test_teacher)
        archived_announcement = baker.make(Announcement, archived=True)
        self.assertContains(self.client.get(reverse('announcements:archived')), archived_announcement.title)

    def test_archived_announcements__are_paginated(self):
        """2nd page after 20 announcements, and view forwards to announcements on 2nd page
        """
        # create enough announcements to create a second page, oldest should be on second page
        for _ in range(21):
            baker.make(Announcement, archived=True, draft=False)

        # Make sure 2nd page exists
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('announcements:archived'))
        self.assertContains(response, "/announcements/archived/?page=2")
        self.assertNotContains(response, "/announcements/archived/?page=3")

    def test_get_absolute_url__for_archived(self):
        """get_absolute_url should redirect/load the proper page with the archived announcement"""
        # create enough announcements to create a second page
        oldest_announcement = baker.make(Announcement, archived=True, draft=False)

        # not paginated:
        self.client.force_login(self.test_teacher)
        response = self.client.get(oldest_announcement.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['archived'])
        self.assertContains(response, oldest_announcement.title)

        # create enough announcements to create a second page, oldest should be on second page
        for _ in range(20):
            baker.make(Announcement, archived=True, draft=False)

        # Make sure the oldest announcement is accessible there
        response = self.client.get("/announcements/archived/?page=2")
        self.assertContains(response, oldest_announcement.title)

        # get_absolute_url still works for archived announcements on second page
        response = self.client.get(oldest_announcement.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, oldest_announcement.title)

    def test_announcement_draft__not_archived_after_semester_close(self):
        """ Draft announcements should not be archived when a semester is closed """
        draft_ann = baker.make(Announcement, archived=False, draft=True)

        self.client.force_login(self.test_teacher)
        self.client.get(reverse('courses:end_active_semester'))

        draft_ann.refresh_from_db()
        self.assertFalse(draft_ann.archived)

    # TODO Fix this, announcements only archive if semester closing is successful, which its not here maybe?
    # def test_announcements_archived_after_semester_close(self):
    #     """ All unarchived (non-draft) announcements should be archived when a semester is closed"""

    #     announcements = [baker.make(Announcement, archived=False, draft=False) for _ in range(5)]

    #     self.client.force_login(self.test_teacher)
    #     self.client.get(reverse('courses:end_active_semester'))

    #     for announcement in announcements:
    #         announcement.refresh_from_db()
    #         self.assertTrue(announcement.archived)
