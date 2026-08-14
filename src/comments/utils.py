from .models import Document


def save_draft_attachments(form, draft_comment):
    """Attach a submission form's validated file uploads to the draft comment, and return how
    many were attached.

    A browser never repopulates a file input, so when a submission fails validation the
    re-rendered page comes back with the "Attach files" input empty: without this the student's
    uploads are gone with nothing to say so, and they submit again believing the files went with
    it (#2427). Attaching them to the draft comment keeps them, and they publish with that
    comment when the submission finally goes through, exactly as they would have on a first-try
    submit.

    Files that failed their own validation (over the size limit) never reach ``cleaned_data``,
    so nothing is stored for them and their error still applies on the retry.

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

    uploads = form.cleaned_data.get("attachments") or []
    for upload in uploads:
        document = Document(docfile=upload, comment=draft_comment)
        document.full_clean()
        document.save()
    return len(uploads)
