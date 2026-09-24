import os

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from model_bakery import baker

from comments.models import Comment, Document
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class CommentAttachmentsTemplateTests(ByteDeckTenantTestCase):
    """A posted comment's attachments, listed as rows of one box the way the submission form
    lists a draft's files (#2752)."""

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

    def attachment_rows(self):
        """The rows the comment's attachments are listed in on the submission page.

        Returns:
            dict: each row's file name (as the page shows it) mapped to the row's <li> tag.
        """
        response = self.client.get(self.submission.get_absolute_url())
        comment = BeautifulSoup(response.content, 'html.parser').find(id=f'comment-{self.comment.id}')
        rows = comment.select('.bt-attachments > .panel > ul.list-group > li.list-group-item')
        return {row.find('a', target='_blank').get_text(strip=True): row for row in rows}

    def test_comments__lists_each_attachment_as_a_row_with_its_paperclip(self):
        """Every attached file is a row of one list group inside a panel, its name a link beside
        a paperclip, rather than an item of a bare bullet list."""
        rows = self.attachment_rows()

        names = {os.path.basename(document.docfile.name) for document in (self.image, self.pdf)}
        self.assertEqual(set(rows), names)
        for row in rows.values():
            self.assertIsNotNone(row.find('a', target='_blank').find('i', class_='fa-paperclip'))

    def test_comments__puts_add_to_portfolio_in_the_row_of_the_file_it_adds(self):
        """Only an image or a video can go in a portfolio, and its button sits in its own row."""
        rows = self.attachment_rows()
        self.assertEqual(len(rows), 2, 'one row per attached file')

        buttons = {name: row.find('a', string='Add to Portfolio') for name, row in rows.items()}
        self.assertIsNotNone(buttons[os.path.basename(self.image.docfile.name)])
        self.assertIsNone(buttons[os.path.basename(self.pdf.docfile.name)])
