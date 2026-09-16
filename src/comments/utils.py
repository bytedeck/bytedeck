import posixpath
import re

from django.core.exceptions import ValidationError

from .models import Document


def accepted_attachments(form):
    """Return the uploads from a submission form's ``attachments`` field that passed validation.

    ``cleaned_data`` holds them when the field as a whole validated. When it did not, the field
    is absent from ``cleaned_data`` entirely: its ``clean()`` validates the selection as a unit,
    so a single file over the size limit takes the rest of that selection down with it. Running
    the field's own clean on each file individually recovers the ones that were fine, leaving
    only the rejected file for the student to choose again.

    Args:
        form: the bound, already-validated submission form.

    Returns:
        list: the accepted uploads, empty if the form has no ``attachments`` field or none of
        the files were acceptable.
    """
    uploads = form.cleaned_data.get("attachments")
    if uploads is not None:
        return uploads

    field = form.fields.get("attachments")
    if field is None:
        return []  # a form without the field at all, such as the quick reply form

    accepted = []
    for upload in form.files.getlist("attachments"):
        try:
            accepted.append(field.clean(upload))
        except ValidationError:
            continue  # this one file is the reason the field failed; its error stands
    return accepted


# The suffix storage adds to a name it already holds: an underscore and seven characters from
# Django's get_random_string (Storage.get_available_name).
STORED_NAME_SUFFIX = re.compile(r"_[A-Za-z0-9]{7}$")


def chosen_name(stored_name):
    """Return the name a stored upload was chosen under.

    Uploads all land in one folder per day, shared by everyone on the deck, and storage will not
    overwrite: a second `photo.jpg` that day is stored as `photo_Ab3dEf7.jpg`. So the stored name
    is not the name the student's browser sent, and taking the suffix back off is what lets an
    upload be recognised as a copy of one already attached.

    A file genuinely named like a suffixed one (`photo_Ab3dEf7.jpg`) reads here as `photo.jpg`.
    The only consequence is in save_draft_attachments, which also requires an exact size match
    before it treats two files as the same upload.

    Args:
        stored_name: the value of a stored ``FileField``, a whole media path.

    Returns:
        str: the bare file name, without the path and without storage's collision suffix.
    """
    stem, extension = posixpath.splitext(posixpath.basename(stored_name))
    return STORED_NAME_SUFFIX.sub("", stem) + extension


def save_draft_attachments(form, draft_comment):
    """Attach a submission form's validated file uploads to the draft comment, and return how
    many were attached.

    A browser never repopulates a file input, so when a submission fails validation the
    re-rendered page comes back with the "Attach files" input empty: without this the student's
    uploads are gone with nothing to say so, and they submit again believing the files went with
    it (#2427). Attaching them to the draft comment keeps them, and they publish with that
    comment when the submission finally goes through, exactly as they would have on a first-try
    submit.

    Only files that passed validation are kept (see ``accepted_attachments``): one rejected for
    being over the size limit is dropped so its error still applies on the retry, while the files
    it was chosen alongside are kept all the same.

    A file the draft already holds is counted as kept without being stored a second time. The
    page clears a file input only when a draft save comes back successfully, so a save whose
    response the browser never saw (a dropped connection part-way through a photo upload, where
    the server stored the file all the same) leaves that file in the input, and the next autosave
    a minute later sends it again. Storing it twice puts the same work in front of the teacher
    twice (#2720). Matched on the name and size the student's browser sent, so a *different* file
    that happens to share a name, such as a corrected version, is still stored.

    Args:
        form: the bound, already-validated submission form (valid or not). Forms without an
            ``attachments`` field (the quick-reply form) contribute nothing.
        draft_comment: the submission's unpublished draft comment, which holds the attachments
            until the submission is completed.

    Returns:
        int: how many files the draft holds as a result, counting any that were already on it.
        Its callers use this to tell the student their uploads survived, which is as true of a
        file that was already stored as of one stored just now.
    """
    # Defensive: an already-completed submission has no draft comment to hold attachments, but
    # its form can only fail validation on the upload itself, and a rejected upload is dropped
    # here anyway. Guarded so a future caller cannot hit an AttributeError.
    if draft_comment is None:  # pragma: no cover
        return 0

    uploads = accepted_attachments(form)
    already_held = {
        (chosen_name(document.docfile.name), document.docfile.size)
        for document in draft_comment.document_set.all()
    }
    for upload in uploads:
        if (upload.name, upload.size) in already_held:
            continue
        document = Document(docfile=upload, comment=draft_comment)
        document.full_clean()
        document.save()
        # the name the student sent, not the stored one: storage appends a suffix to a name it
        # already has, so the stored name would no longer match the next copy of this upload
        already_held.add((upload.name, upload.size))
    return len(uploads)
