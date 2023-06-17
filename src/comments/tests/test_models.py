from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from comments.models import Comment, clean_html

User = get_user_model()


class CommentManagerTest(TenantTestCase):

    def test_create_comment__with_required_parameters(self):
        user = baker.make(User)
        path = "/some/path/"
        text = "This is a comment."
        comment = Comment.objects.create_comment(user=user, text=text, path=path)

        self.assertEqual(comment.user, user)
        self.assertEqual(comment.text, text)
        self.assertEqual(comment.path, path + "#comment-" + str(comment.id))
        self.assertIsNone(comment.target_content_type)
        self.assertIsNone(comment.target_object_id)
        self.assertIsNone(comment.parent)

    def test_create_comment__without_path(self):
        user = baker.make(User)
        text = "This is a comment."
        with self.assertRaises(ValueError) as cm:
            Comment.objects.create_comment(user=user, text=text)
        self.assertEqual(str(cm.exception), "Must include a path when adding a comment")

    def test_create_comment__without_user(self):
        path = "/some/path/"
        text = "This is a comment."
        with self.assertRaises(ValueError) as cm:
            Comment.objects.create_comment(text=text, path=path)
        self.assertEqual(str(cm.exception), "Must include a user when adding a comment")

    def test_create_comment__with_all_parameters(self):
        user = User.objects.create(username="testuser")
        path = "/some/path/"
        text = "This is a comment."
        target = baker.make('announcements.Announcement')
        parent = Comment.objects.create(user=user, text="Parent Comment", path="/some/parent/")
        comment = Comment.objects.create_comment(user=user, text=text, path=path, target=target, parent=parent)

        self.assertEqual(comment.user, user)
        self.assertEqual(comment.text, text)
        self.assertEqual(comment.path, path + "#comment-" + str(comment.id))
        self.assertEqual(comment.target_content_type, ContentType.objects.get_for_model(target))
        self.assertEqual(comment.target_object_id, target.id)
        self.assertEqual(comment.parent, parent)


class CleanHTMLTests(TestCase):
    def test_format_unformatted_links(self):
        text = '<p>Visit my website: example.com</p>'
        expected_output = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_skip_formatted_links(self):
        text = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        expected_output = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_set_links_target_blank(self):
        text = '<a href="http://example.com">Link</a>'
        expected_output = '<a href="http://example.com" target="_blank">Link</a>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_fix_missing_closing_ul_tag(self):
        """ TODO: Test passes but the function isn't very good.
        Closes the list in the wrong place.  Need to fix the function."""
        text = '<ul><li>Item 1</li><p>Paragraph</p>'
        expected_output = '<ul><li>Item 1</li><p>Paragraph</p></ul>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_remove_script_tags(self):
        text = '<p>Some text<script>alert("Hello");</script></p>'
        expected_output = '<p>Some text</p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)


class CommentModelTest(TenantTestCase):

    def setUp(self):
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)

    def test_comment_creation(self):
        comment = baker.make(Comment)
        self.assertIsInstance(comment, Comment)
        self.assertEqual(str(comment), comment.text)

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

    def test_flag(self):
        comment = baker.make(Comment)
        self.assertFalse(comment.flagged)
        comment.flag()
        self.assertTrue(comment.flagged)

    def test_unflag(self):
        comment = baker.make(Comment, flagged=True)
        self.assertTrue(comment.flagged)
        comment.unflag()
        self.assertFalse(comment.flagged)

    def test_get_origin(self):
        comment = baker.make(Comment)
        self.assertEqual(comment.get_origin(), comment.path)

    def test_is_child(self):
        parent = baker.make(Comment)
        child = baker.make(Comment, parent=parent)
        self.assertTrue(child.is_child())
        self.assertFalse(parent.is_child())

    def test_get_children(self):
        "Test that method returns a queryset including all children"
        parent = baker.make(Comment)

        self.assertQuerysetEqual(parent.get_children(), [])

        child = baker.make(Comment, parent=parent)
        self.assertIsNone(child.get_children())

        child2 = baker.make(Comment, parent=parent)
        children = parent.get_children()
        self.assertQuerysetEqual(children, [child, child2], ordered=False)
