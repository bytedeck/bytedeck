import os
import shutil
import tempfile

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings
from model_bakery import baker

from comments.models import Comment, Document
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class CommentAttachmentsTemplateTests(ByteDeckTenantTestCase):
    """A posted comment's attachments: a bulleted list, set apart from the comment by one rule
    (#2752). The submission form lists a draft's files the same way."""

    @classmethod
    def setUpClass(cls):
        """Keep the attached files in a throwaway MEDIA_ROOT, out of the project's own."""
        cls._temp_media = tempfile.mkdtemp(prefix='test-media-comment-attachments-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._temp_media, ignore_errors=True)
        super().setUpClass()

    def setUp(self):
        """A student's posted comment on their submission, with an image and a PDF attached, and
        a teacher signed in to read it."""
        student = baker.make(User)
        self.submission = baker.make('quest_manager.QuestSubmission', user=student)
        self.comment = Comment.objects.create_comment(
            user=student, path='/some/path/', text='here is my work', target=self.submission)
        self.image = self.attach('poster.png')
        self.pdf = self.attach('statement.pdf')
        self.client.force_login(baker.make(User, is_staff=True))

    def attach(self, name):
        """Attach a stored file to the comment.

        Args:
            name (str): the file name to store it under.

        Returns:
            Document: the row holding the stored file.
        """
        document = Document(comment=self.comment)
        document.docfile.save(name, ContentFile(b'file_content'), save=True)
        return document

    def comment_markup(self):
        """The comment as the submission page draws it.

        Returns:
            Tag: the comment's <li>, parsed.
        """
        response = self.client.get(self.submission.get_absolute_url())
        return BeautifulSoup(response.content, 'html.parser').find(id=f'comment-{self.comment.id}')

    def test_comments__lists_each_attachment_as_a_bullet(self):
        """Every attached file is an item of a bulleted list, its name a link, and only the image
        (a file a portfolio can take) has Add to Portfolio beside it."""
        items = {
            item.find('a', target='_blank').get_text(strip=True): item
            for item in self.comment_markup().select('ul.file-links > li.file-link')
        }

        image, pdf = (os.path.basename(document.docfile.name) for document in (self.image, self.pdf))
        self.assertEqual(set(items), {image, pdf})
        self.assertIsNotNone(items[image].find('a', string='Add to Portfolio'))
        self.assertIsNone(items[pdf].find('a', string='Add to Portfolio'))

    def test_comments__one_rule_sets_the_files_apart(self):
        """A comment of its author's words alone has one rule, between them and its files."""
        comment = self.comment_markup()

        rules = comment.find_all('hr')
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].find_next('p').get_text(strip=True), 'Attached files:')

    def test_comments__details_keep_their_own_rule_and_the_files_follow(self):
        """A comment ending with details under a rule of its own (a quest's hand-in choices) keeps
        that one rule only: its files follow the details with no second one (#2752)."""
        self.comment.text = (
            '<p>here is my work</p><hr class="tighter"/>'
            '<ul class="comment-details"><li><b>XP requested: 5</b></li></ul>'
        )
        self.comment.save()

        comment = self.comment_markup()

        rules = comment.find_all('hr')
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].find_next('ul').get_text(strip=True), 'XP requested: 5')
        self.assertEqual(len(comment.select('ul.file-links > li.file-link')), 2)
