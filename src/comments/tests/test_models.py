from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from model_bakery import baker
from model_bakery.recipe import Recipe

from comments.models import Comment, clean_html
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class CommentManagerTest(ByteDeckTenantTestCase):

    def test_create_comment__with_required_parameters(self):
        """create_comment() with only user, text, and path leaves the target and parent unset."""
        user = baker.make(User)
        path = "/some/path/"
        text = "This is a comment."
        comment = Comment.objects.create_comment(user=user, text=text, path=path)

        self.assertEqual(comment.user, user)
        self.assertEqual(comment.text, text)
        self.assertEqual(comment.path, f"{path}#comment-{comment.id}")
        self.assertIsNone(comment.target_content_type)
        self.assertIsNone(comment.target_object_id)
        self.assertIsNone(comment.parent)

    def test_create_comment__without_path(self):
        """create_comment() raises ValueError when no path is provided."""
        user = baker.make(User)
        text = "This is a comment."
        with self.assertRaises(ValueError) as cm:
            Comment.objects.create_comment(user=user, text=text)
        self.assertEqual(str(cm.exception), "Must include a path when adding a comment")

    def test_create_comment__without_user(self):
        """create_comment() raises ValueError when no user is provided."""
        path = "/some/path/"
        text = "This is a comment."
        with self.assertRaises(ValueError) as cm:
            Comment.objects.create_comment(text=text, path=path)
        self.assertEqual(str(cm.exception), "Must include a user when adding a comment")

    def test_create_comment__with_all_parameters(self):
        """create_comment() stores the target content type/object id and parent when supplied."""
        user = User.objects.create(username="testuser")
        path = "/some/path/"
        text = "This is a comment."
        target = baker.make('announcements.Announcement')
        parent = Comment.objects.create(user=user, text="Parent Comment", path="/some/parent/")
        comment = Comment.objects.create_comment(user=user, text=text, path=path, target=target, parent=parent)

        self.assertEqual(comment.user, user)
        self.assertEqual(comment.text, text)
        self.assertEqual(comment.path, f"{path}#comment-{comment.id}")
        self.assertEqual(comment.target_content_type, ContentType.objects.get_for_model(target))
        self.assertEqual(comment.target_object_id, target.id)
        self.assertEqual(comment.parent, parent)

    def test_create_comment__empty_text_is_allowed(self):
        """A draft comment (e.g. a quest submission's draft_comment) is created empty before
        the student types anything, so empty text must pass full_clean() (issue #1630).
        """
        comment = Comment.objects.create_comment(user=baker.make(User), text="", path="/some/path/")
        self.assertEqual(comment.text, "")

    def test_create_comment__invalid_data_raises_validation_error(self):
        """create_comment() runs full_clean(), so invalid data raises ValidationError rather
        than being silently saved (issue #1630).
        """
        user = baker.make(User)
        with self.assertRaises(ValidationError):
            # path exceeds the model's max_length of 350
            Comment.objects.create_comment(user=user, text="hi", path="/" + "x" * 400)


class CommentModelValidationTest(ByteDeckTenantTestCase):
    """flag()/unflag() validate the comment before saving (issue #1630)."""

    def setUp(self):
        """Create a valid comment used by each validation test."""
        self.comment = Comment.objects.create_comment(user=baker.make(User), text="hi", path="/some/path/")

    def test_flag__runs_full_clean(self):
        """flag() calls full_clean() before save(), so an invalid comment raises."""
        self.comment.path = "/" + "x" * 400  # now exceeds max_length
        with self.assertRaises(ValidationError):
            self.comment.flag()

    def test_unflag__runs_full_clean(self):
        """unflag() calls full_clean() before save(), so an invalid comment raises."""
        self.comment.flagged = True
        self.comment.path = "/" + "x" * 400  # now exceeds max_length
        with self.assertRaises(ValidationError):
            self.comment.unflag()


class CleanHTMLTests(TestCase):
    def test_clean_html__formats_unformatted_links(self):
        """Bare URLs in text are wrapped in anchor tags opening in a new tab."""
        text = '<p>Visit my website: example.com</p>'
        expected_output = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_clean_html__skips_already_formatted_links(self):
        """Existing anchor tags are left unchanged."""
        text = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        expected_output = '<p>Visit my website: <a href="http://example.com" target="_blank">example.com</a></p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_clean_html__sets_links_target_blank(self):
        """Anchor tags without a target get target="_blank" added."""
        text = '<a href="http://example.com">Link</a>'
        expected_output = '<a href="http://example.com" target="_blank">Link</a>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_clean_html__fixes_missing_closing_ul_tag(self):
        """ TODO: Test passes but the function isn't very good.
        Closes the list in the wrong place.  Need to fix the function."""
        text = '<ul><li>Item 1</li><p>Paragraph</p>'
        expected_output = '<ul><li>Item 1</li><p>Paragraph</p></ul>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)

    def test_clean_html__removes_script_tags(self):
        """Script tags and their contents are stripped from the html."""
        text = '<p>Some text<script>alert("Hello");</script></p>'
        expected_output = '<p>Some text</p>'
        cleaned_text = clean_html(text)
        self.assertEqual(cleaned_text, expected_output)


class CommentModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and student shared across the test methods."""
        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)

    def test_comment_creation__str_returns_text(self):
        """A comment is created and its string representation is its text."""
        comment = baker.make(Comment)
        self.assertIsInstance(comment, Comment)
        self.assertEqual(str(comment), comment.text)

    def test_get_absolute_url__returns_url(self):
        """A comment exposes a non-null absolute url."""
        comment = baker.make(Comment)
        self.assertIsInstance(comment, Comment)
        self.assertEqual(str(comment), comment.text)
        self.assertIsNotNone(comment.get_absolute_url())

    def test_orphaned_li_tags__wrapped_in_ul(self):
        """Orphaned <li> tags in comment text are wrapped in a <ul> on save."""
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

    def test_script_removal__strips_script_tags(self):
        """Script tags in comment text are removed on save."""
        bad_text = "<p>stuff</p><script>do bad stuff</script>"

        comment = Comment.objects.create_comment(
            user=self.student,
            text=bad_text,
            path="nothing",
        )

        self.assertNotIn("<script>", comment.text)

    def test_comment_text__unchanged_for_valid_html(self):
        """Valid html in comment text is preserved unchanged."""
        text = "<p>This is some good html snippet that shouldn't be changed</p>"

        comment = Comment.objects.create_comment(
            user=self.student,
            text=text,
            path="nothing",
            target=None,
            parent=None,
        )

        self.assertHTMLEqual(comment.text, text)

    def test_flag__sets_flagged_true(self):
        """flag() marks an unflagged comment as flagged."""
        comment = baker.make(Comment)
        self.assertFalse(comment.flagged)
        comment.flag()
        self.assertTrue(comment.flagged)

    def test_unflag__sets_flagged_false(self):
        """unflag() clears the flagged state of a flagged comment."""
        comment = baker.make(Comment, flagged=True)
        self.assertTrue(comment.flagged)
        comment.unflag()
        self.assertFalse(comment.flagged)

    def test_get_origin__returns_path(self):
        """get_origin() returns the comment's path."""
        comment = baker.make(Comment)
        self.assertEqual(comment.get_origin(), comment.path)

    def test_is_child__true_only_for_child(self):
        """is_child() is true for a comment with a parent and false otherwise."""
        parent = baker.make(Comment)
        child = baker.make(Comment, parent=parent)
        self.assertTrue(child.is_child())
        self.assertFalse(parent.is_child())

    def test_get_children__returns_all_children(self):
        "Test that method returns a queryset including all children"
        parent = baker.make(Comment)

        self.assertQuerySetEqual(parent.get_children(), [])

        child = baker.make(Comment, parent=parent)
        self.assertIsNone(child.get_children())

        child2 = baker.make(Comment, parent=parent)
        children = parent.get_children()
        self.assertQuerySetEqual(children, [child, child2], ordered=False)
