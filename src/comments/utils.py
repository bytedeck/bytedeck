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

    Args:
        form: the bound, already-validated submission form (valid or not). Forms without an
            ``attachments`` field (the quick-reply form) contribute nothing.
        draft_comment: the submission's unpublished draft comment, which holds the attachments
            until the submission is completed.

    Returns:
        int: how many files were attached.
    """
    # Defensive: an already-completed submission has no draft comment to hold attachments, but
    # its form can only fail validation on the upload itself, and a rejected upload is dropped
    # here anyway. Guarded so a future caller cannot hit an AttributeError.
    if draft_comment is None:  # pragma: no cover
        return 0

    uploads = accepted_attachments(form)
    for upload in uploads:
        document = Document(docfile=upload, comment=draft_comment)
        document.full_clean()
        document.save()
    return len(uploads)
