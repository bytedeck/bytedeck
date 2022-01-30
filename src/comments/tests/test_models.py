from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from comments.models import Comment


class CommentTestModel(TenantTestCase):

    def setUp(self):
        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)

    def test_comment_creation(self):
        comment = baker.make(Comment)
        self.assertIsInstance(comment, Comment)
        # self.assertEqual(str("Test"), self.submission.quest.name)

    def test_orphaned_li_tags(self):
        bad_comment_texts = [
            "<li>1</li><li>2</li>",
            "<div><li>1</li><li>2</li>",
            "<p></p><li>1</li><li>2</li>",
            "<p></p><li>1<P>asdasd</p></li><br><li>2</li>"
        ]

        for bad_text in bad_comment_texts:
            comment = Comment.objects.create_comment(
                user=self.student,
                text=bad_text,
                path="nothing",
            )

            self.assertIn("<ul>", comment.text)
            self.assertIn("</ul>", comment.text)

    def test_script_removal(self):
        bad_text = "<p>stuff</p><script>do bad stuff</script>"

        comment = Comment.objects.create_comment(
            user=self.student,
            text=bad_text,
            path="nothing",
        )

        self.assertNotIn("<script>", comment.text)

    def test_comment_text_unchanged(self):
        text = "<p>This is some good html snippet that shouldn't be changed</p>"

        comment = Comment.objects.create_comment(
            user=self.student,
            text=text,
            path="nothing",
            target=None,
            parent=None,
        )

        self.assertHTMLEqual(comment.text, text)
