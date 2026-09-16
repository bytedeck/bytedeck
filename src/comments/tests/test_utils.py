from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict

from model_bakery import baker

from comments.models import Comment
from comments.utils import chosen_name, save_draft_attachments
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

    def test_save_draft_attachments__does_not_store_a_file_the_draft_already_holds(self):
        """The same upload arriving twice leaves the draft holding it once (#2720).

        A draft save whose response the browser never saw leaves the file in the input, so the
        next autosave sends it again; the student's work must not reach their teacher twice.
        The return value still counts it, because their upload did survive.
        """
        save_draft_attachments(
            self.bound_form([SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")]),
            self.draft_comment,
        )

        again = self.bound_form([SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")])

        self.assertEqual(save_draft_attachments(again, self.draft_comment), 1)
        self.assertEqual(self.draft_comment.document_set.count(), 1)

    def test_save_draft_attachments__stores_a_different_file_of_the_same_name(self):
        """Only a copy of what the draft already holds is skipped. A student attaching a corrected
        version under the same name still gets it stored, so nothing is dropped silently."""
        save_draft_attachments(
            self.bound_form([SimpleUploadedFile("notes.txt", b"first version", content_type="text/plain")]),
            self.draft_comment,
        )

        corrected = self.bound_form(
            [SimpleUploadedFile("notes.txt", b"a longer, corrected version", content_type="text/plain")])

        self.assertEqual(save_draft_attachments(corrected, self.draft_comment), 1)
        self.assertEqual(self.draft_comment.document_set.count(), 2)

    def test_save_draft_attachments__the_same_upload_is_stored_once_per_draft(self):
        """Skipping is scoped to the one draft. Another student attaching an identical file to
        their own submission stores it, rather than being denied a file because someone else
        already has one like it."""
        save_draft_attachments(
            self.bound_form([SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")]),
            self.draft_comment,
        )
        someone_elses_draft = Comment.objects.create_comment(
            user=baker.make(User), path="/another/path/", text="", target=None)

        form = self.bound_form([SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")])

        self.assertEqual(save_draft_attachments(form, someone_elses_draft), 1)
        self.assertEqual(someone_elses_draft.document_set.count(), 1)


class ChosenNameTest(ByteDeckTenantTestCase):
    """Tests for comments.utils.chosen_name(), which recovers the name an upload was chosen
    under from the name it ended up stored as."""

    def test_chosen_name__strips_the_path(self):
        """A stored FileField value is a whole media path; only the file name identifies it."""
        self.assertEqual(chosen_name("documents/2026/09/15/notes.txt"), "notes.txt")

    def test_chosen_name__strips_storages_collision_suffix(self):
        """Storage appends an underscore and seven random characters to a name it already holds,
        which every deck hits because a day's uploads share one folder."""
        self.assertEqual(chosen_name("documents/2026/09/15/notes_Ab3dEf7.txt"), "notes.txt")

    def test_chosen_name__leaves_an_ordinary_underscore_alone(self):
        """Only a suffix of exactly seven characters is storage's. An underscore in the student's
        own file name is part of the name they chose."""
        self.assertEqual(chosen_name("documents/2026/09/15/my_notes.txt"), "my_notes.txt")
        self.assertEqual(chosen_name("documents/2026/09/15/notes_v2.txt"), "notes_v2.txt")

    def test_chosen_name__copes_with_a_name_that_has_no_extension(self):
        """A file chosen without an extension still has a name, suffixed or not."""
        self.assertEqual(chosen_name("documents/2026/09/15/README"), "README")
        self.assertEqual(chosen_name("documents/2026/09/15/README_Ab3dEf7"), "README")
