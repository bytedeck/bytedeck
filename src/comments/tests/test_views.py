from django.contrib.auth import get_user_model
from django.urls import reverse

from unittest.mock import patch
from model_bakery import baker
from comments.models import Comment
from bs4 import BeautifulSoup

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class CommentViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create users, an announcement, and comments shared across the test methods."""
        cls.student = baker.make(User)
        cls.teacher = baker.make(User, is_staff=True)
        cls.announcement = baker.make('announcements.Announcement')
        # create a test comment on the test announcement. Null the GFK explicitly
        # (these comments are attached by path, not a target object) so baker
        # doesn't fill target_content_type with a random -- possibly table-less --
        # model, which would make str()/rendering non-deterministic under a
        # reused schema.
        cls.comment = baker.make(
            'comments.Comment', user=cls.student, path=cls.announcement.get_absolute_url(),
            target_content_type=None,
        )
        cls.comment_decoy = baker.make('comments.Comment', target_content_type=None)

    @patch('comments.models.Comment.unflag')
    def test_unflag__staff_only_calls_unflag(self, mock_unflag):
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
    def test_flag__staff_only_calls_flag(self, mock_flag):
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
    def test_delete__staff_only_removes_comment(self, mock_flag):
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

    def test_comment_content__has_user_content_class(self):
        """Rendered comment bodies carry the `user-content` class (#1388).

        Comments live inside a Bootstrap `.list-group`, which is itself a `<ul>`, so a
        bullet/number list typed into a comment would otherwise be treated as a *nested*
        list and marked with the hollow level-2 style. The `.user-content` class re-establishes
        depth-correct markers (solid disc at the first level) via custom_common.css.
        """
        Comment.objects.create_comment(
            user=self.teacher,
            text="<ul><li>a bullet</li></ul>",
            path=self.announcement.get_absolute_url(),
            target=self.announcement,
        )
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('announcements:list'))
        self.assertContains(response, 'comment-content user-content')

    def test_delete_comment__cancel_button_path(self):
        ''' Test if the 'Cancel' button in src/comments/templates/comments/confirm_delete.html
        correctly contains the `comment.path` as its href attribute.
        '''
        self.client.force_login(self.teacher)

        # get confirm delete content html
        response = self.client.get(reverse('comments:delete', args=[self.comment.id]))
        self.assertContains(response, 'Cancel')

        soup = BeautifulSoup(response.content.decode('utf-8'), features='html.parser')

        # find the Cancel Button
        tag = soup.find('a', href=self.announcement.get_absolute_url(), role='button', text='Cancel')
        self.assertIsNotNone(tag)
