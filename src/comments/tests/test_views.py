from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from unittest.mock import patch
from model_bakery import baker
from comments.models import Comment

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class CommentViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.student = baker.make(User)
        self.teacher = baker.make(User, is_staff=True)
        self.announcement = baker.make('announcements.Announcement')
        # create a test comment on the test announcement
        self.comment = baker.make('comments.Comment', user=self.student, path=self.announcement.get_absolute_url())
        self.comment_decoy = baker.make('comments.Comment')
        self.client = TenantClient(self.tenant)

    @patch('comments.models.Comment.unflag')
    def test_unflag(self, mock_unflag):
        """Test that unflag view is only accessible to staff users,
        and that it calls the unflag method on the comment and redirects to the comment's path
        """

        # Anonymous user
        self.assertRedirectsLogin('comments:unflag', args=[self.comment.id])
        mock_unflag.assert_not_called()

        # student can't access this view
        self.client.force_login(self.student)
        self.assert403('comments:unflag', args=[self.comment.id])
        mock_unflag.assert_not_called()

        # teacher can access this view
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('comments:unflag', args=[self.comment.id]))
        self.assertRedirects(response, self.comment.path)
        mock_unflag.assert_called_once()

    @patch('comments.models.Comment.flag')
    def test_flag(self, mock_flag):
        """Test that unflag view is only accessible to staff users,
        and that it calls the flag method on the comment and redirects to the comment's path
        """

        # Anonymous user
        self.assertRedirectsLogin('comments:flag', args=[self.comment.id])
        mock_flag.assert_not_called()

        # student can't access this view
        self.client.force_login(self.student)
        self.assert403('comments:flag', args=[self.comment.id])
        mock_flag.assert_not_called()

        # teacher can access this view
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('comments:flag', args=[self.comment.id]))
        self.assertRedirects(response, self.comment.path)
        mock_flag.assert_called_once()

    @patch('comments.models.Comment.flag')
    def test_delete(self, mock_flag):
        """Test that delete view is only accessible to staff users,
        and that deletes the comment and redirects tot he comments (former) path
        """

        # Anonymous user
        self.assertRedirectsLogin('comments:delete', args=[self.comment.id])
        self.assertTrue(Comment.objects.filter(id=self.comment.id).exists())

        # student can't access this view
        self.client.force_login(self.student)
        self.assert403('comments:delete', args=[self.comment.id])
        self.assertTrue(Comment.objects.filter(id=self.comment.id).exists())

        # teacher can access this view
        self.client.force_login(self.teacher)

        # Get request redirect to confirmation page
        response = self.assert200('comments:delete', args=[self.comment.id])
        # Check that the response uses the expected template
        self.assertTemplateUsed(response, 'comments/confirm_delete.html')

        # delete_me_comment = baker.make('comments.Comment', path=self.announcement.get_absolute_url())
        path = self.comment.path

        # Post request deletes the comment and redirects to the comments path
        response = self.client.post(reverse('comments:delete', args=[self.comment.id]))
        self.assertRedirects(response, path)
        self.assertFalse(Comment.objects.filter(id=self.comment.id).exists())
