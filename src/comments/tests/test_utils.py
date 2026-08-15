from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict

from model_bakery import baker

from comments.models import Comment
from comments.utils import save_draft_attachments
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.forms import SubmissionForm, SubmissionQuickReplyFormStudent

User = get_user_model()


class SaveDraftAttachmentsTest(ByteDeckTenantTestCase):
    """Tests for comments.utils.save_draft_attachments(), which keeps a submission's uploaded
    attachments on its draft comment when the submission fails validation (#2427)."""

    def setUp(self):
        """A draft comment to hang attachments off, built the way the submission view builds it."""
        self.draft_comment = Comment.objects.create_comment(
            user=baker.make(User), path="/some/path/", text="", target=None)

    def bound_form(self, uploads, form_class=SubmissionForm):
        """Return a validated submission form bound to the given uploads, the way complete()
        binds it to request.POST and request.FILES."""
        form = form_class(data={"comment_text": ""}, files=MultiValueDict({"attachments": uploads}))
        form.is_valid()  # the helper runs on an already-validated form, valid or not
        return form

    def test_save_draft_attachments__attaches_validated_uploads(self):
        """Every upload that passed validation becomes a Document on the draft comment."""
        uploads = [
            SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain"),
            SimpleUploadedFile("diagram.png", b"file_content", content_type="image/png"),
        ]

        saved = save_draft_attachments(self.bound_form(uploads), self.draft_comment)

        self.assertEqual(saved, 2)
        names = [document.docfile.name for document in self.draft_comment.document_set.all()]
        self.assertEqual(len(names), 2)
        self.assertTrue(any("notes" in name for name in names), names)
        self.assertTrue(any("diagram" in name for name in names), names)

    def test_save_draft_attachments__skips_an_upload_that_failed_validation(self):
        """An upload over the form's size limit is not kept, so its error still applies on the retry.

        Storing a rejected file would let the student submit again without fixing it, and it would
        then publish with their comment despite never having been accepted.
        """
        too_big = SimpleUploadedFile("huge.png", b"file_content", content_type="image/png")
        # claim a size over the form field's 16MB limit without allocating 16MB in the test
        too_big.size = 16777217

        form = self.bound_form([too_big])

        self.assertFalse(form.is_valid())
        self.assertEqual(save_draft_attachments(form, self.draft_comment), 0)
        self.assertEqual(self.draft_comment.document_set.count(), 0)

    def test_save_draft_attachments__keeps_the_good_files_of_a_mixed_selection(self):
        """One oversized file does not cost the student the files chosen alongside it.

        The field validates the whole selection at once, so a single rejected file leaves
        `attachments` out of cleaned_data entirely; the acceptable files still have to be kept,
        or a student who attached five files and one too-large one loses all six.
        """
        good = SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")
        too_big = SimpleUploadedFile("huge.png", b"file_content", content_type="image/png")
        # claim a size over the form field's 16MB limit without allocating 16MB in the test
        too_big.size = 16777217

        form = self.bound_form([good, too_big])

        self.assertFalse(form.is_valid())
        self.assertEqual(save_draft_attachments(form, self.draft_comment), 1)
        kept = self.draft_comment.document_set.get()
        self.assertIn("notes", kept.docfile.name)

    def test_save_draft_attachments__form_without_an_attachments_field(self):
        """A form that has no attachments field (the quick reply form) contributes nothing.

        complete() uses the quick reply form when the POST carries no files at all, so the helper
        has to cope with a form that never had the field.
        """
        form = SubmissionQuickReplyFormStudent(data={"comment_text": "just a comment"})
        form.is_valid()

        self.assertEqual(save_draft_attachments(form, self.draft_comment), 0)
        self.assertEqual(self.draft_comment.document_set.count(), 0)
