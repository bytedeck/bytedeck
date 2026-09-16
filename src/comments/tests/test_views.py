from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from unittest.mock import patch
from model_bakery import baker
from comments.models import Comment, Document
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


class DocumentDownloadViewTests(ByteDeckTenantTestCase):
    """Serving a script-capable attachment as a download.

    The submission comment's "Attach files" box takes web files, because quests ask students to
    hand in a page or a vector drawing through it. Opened inline from the app's own origin such
    a file runs its script in the session of whoever follows the link, normally the teacher
    marking the work, so the app links those through here instead (#2726).
    """

    def setUp(self):
        """A student with a comment, and an attachment on it to serve."""
        self.student = baker.make(User)
        self.comment = Comment.objects.create_comment(
            user=self.student, path="/some/path/", text="here is my work", target=None)
        self.client.force_login(self.student)

    def attach(self, name, content=b"<svg xmlns='http://www.w3.org/2000/svg'/>"):
        """Attach a stored file to the comment.

        Args:
            name: the file name to store it under.
            content: the bytes to store.

        Returns:
            Document: the row holding the stored file.
        """
        document = Document(comment=self.comment)
        document.docfile.save(name, ContentFile(content), save=True)
        return document

    def download(self, document_id):
        """GET the download for one attachment.

        Args:
            document_id: pk of the Document to fetch, valid or not.

        Returns:
            HttpResponse: what the view answered.
        """
        return self.client.get(reverse('comments:document_download', args=[document_id]))

    def test_document_download__serves_an_svg_as_an_attachment(self):
        """The browser is told to save the file rather than render it, which is what stops the
        script inside it running as the viewer."""
        document = self.attach("drawing.svg")

        response = self.download(document.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        # the stored name, which carries storage's suffix when a file of that name already
        # exists in the day's folder, so only the stem and the extension are asserted
        self.assertIn("drawing", response["Content-Disposition"])
        self.assertIn(".svg", response["Content-Disposition"])

    def test_document_download__serves_a_web_page_as_an_attachment(self):
        """A handed-in HTML page is the other file this exists for."""
        document = self.attach("index.html", b"<!doctype html><title>my page</title>")

        response = self.download(document.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_document_download__an_image_is_not_served_this_way(self):
        """An image is linked at its storage url and has to keep opening in a tab, so it is not
        one of the files this serves: a teacher marking a photo should not be made to download
        it first."""
        document = self.attach("photo.png", b"file_content")

        self.assertEqual(self.download(document.id).status_code, 404)

    def test_document_download__unknown_attachment_is_a_404(self):
        """An id with no attachment behind it 404s rather than erroring."""
        self.assertEqual(self.download(0).status_code, 404)

    def test_document_download__anonymous_is_sent_to_login(self):
        """Signing in is required, as it is everywhere else on a deck."""
        document = self.attach("drawing.svg")
        self.client.logout()

        self.assertRedirectsLogin('comments:document_download', args=[document.id])

    def test_get_download_url__script_capable_attachment_goes_through_the_download_view(self):
        """What the templates link, for the file that must not open in the page."""
        document = self.attach("drawing.svg")

        self.assertEqual(
            document.get_download_url(),
            reverse('comments:document_download', args=[document.id]),
        )

    def test_get_download_url__an_ordinary_attachment_keeps_its_storage_url(self):
        """Everything else is linked as before, so nothing about marking an image changes."""
        document = self.attach("photo.png", b"file_content")

        self.assertEqual(document.get_download_url(), document.docfile.url)

    def test_comments_template__links_a_script_capable_attachment_at_the_download_view(self):
        """The rendered comment thread is where the link the teacher clicks actually comes from,
        so the storage url must not be in it."""
        submission = baker.make('quest_manager.QuestSubmission', user=self.student)
        self.comment.target_object = submission
        self.comment.save()
        document = self.attach("drawing.svg")
        self.client.force_login(baker.make(User, is_staff=True))

        response = self.client.get(submission.get_absolute_url())

        self.assertContains(response, reverse('comments:document_download', args=[document.id]))
        self.assertNotContains(response, document.docfile.url)

    def test_document_download__the_submissions_own_student_may_fetch_it(self):
        """A teacher's attached example on a student's own submission stays theirs to open, so
        the check cannot be just "the person who wrote the comment"."""
        submission = baker.make('quest_manager.QuestSubmission', user=self.student)
        teachers_comment = Comment.objects.create_comment(
            user=baker.make(User, is_staff=True), path="/some/path/", text="here is an example",
            target=submission)
        document = Document(comment=teachers_comment)
        document.docfile.save("example.svg", ContentFile(b"<svg/>"), save=True)

        self.assertEqual(self.download(document.id).status_code, 200)

    def test_document_download__another_student_may_not_fetch_it(self):
        """A url carrying a row id is guessable in a way a storage path is not, so a classmate
        cannot walk the ids and pull down everyone's work."""
        submission = baker.make('quest_manager.QuestSubmission', user=baker.make(User))
        someone_elses = Comment.objects.create_comment(
            user=submission.user, path="/some/path/", text="my work", target=submission)
        document = Document(comment=someone_elses)
        document.docfile.save("theirs.svg", ContentFile(b"<svg/>"), save=True)

        self.assertEqual(self.download(document.id).status_code, 404)

    def test_document_download__staff_may_fetch_any_of_them(self):
        """Marking the work is the whole point of the link."""
        submission = baker.make('quest_manager.QuestSubmission', user=baker.make(User))
        someone_elses = Comment.objects.create_comment(
            user=submission.user, path="/some/path/", text="my work", target=submission)
        document = Document(comment=someone_elses)
        document.docfile.save("theirs.svg", ContentFile(b"<svg/>"), save=True)
        self.client.force_login(baker.make(User, is_staff=True))

        self.assertEqual(self.download(document.id).status_code, 200)

    def test_document_download__an_announcement_attachment_is_the_whole_decks(self):
        """An announcement thread is visible to everyone on the deck, so its attachments are
        too: the check must not lock students out of one."""
        announcement = baker.make('announcements.Announcement', author=baker.make(User, is_staff=True))
        thread_comment = Comment.objects.create_comment(
            user=announcement.author, path="/some/path/", text="see attached", target=announcement)
        document = Document(comment=thread_comment)
        document.docfile.save("notice.svg", ContentFile(b"<svg/>"), save=True)

        self.assertEqual(self.download(document.id).status_code, 200)

    def test_document_download__an_attachment_on_no_comment_belongs_to_nobody(self):
        """A Document with no comment is part of no thread, so there is nobody it is visible to
        and its NULL must not be matched against anything."""
        orphan = Document(comment=None)
        orphan.docfile.save("orphan.svg", ContentFile(b"<svg/>"), save=True)

        self.assertEqual(self.download(orphan.id).status_code, 404)
