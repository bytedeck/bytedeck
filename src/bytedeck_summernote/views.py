from django.http import QueryDict

from django_summernote.views import SummernoteEditor, SummernoteUploadAttachment


class ByteDeckSummernoteEditor(SummernoteEditor):
    """
    Override `SummernoteEditor` class to use customized template file (mandatory for ByteDeck project)
    """

    template_name = "bytedeck_summernote/widget_iframe_editor.html"


class ByteDeckSummernoteUploadAttachment(SummernoteUploadAttachment):
    """
    Summernote's image upload, saving each image without the fields posted beside it.

    The editor's upload script posts the textarea's ``data-*`` attributes along with the images
    (``origin.dataset`` in django-summernote's ``widget_common.html``), and django-summernote's view
    passes every posted field but the CSRF token to ``attachment.save()`` as a keyword argument, for
    custom attachment models whose ``save()`` takes extra ones. The stock ``Attachment`` takes none,
    so any data attribute on the textarea failed the upload with a ``TypeError``. The app puts none
    there, but browser add-ons can: the accessiBe accessibility overlay marks elements
    ``data-acsb-navigable`` and so on (#1555). Nothing posted is meant for ``save()``, so the
    view is handed no fields at all.
    """

    def post(self, request, *args, **kwargs):
        """Clear the posted fields, keeping the uploaded images, then save them as django-summernote does."""
        # Django parses an upload's fields and files together, on the first read of either. Read them before
        # clearing the fields, since a first read afterwards would parse the fields back in. RequestDataTooBigMiddleware
        # reads them before any view as it is, but this view doesn't rely on that.
        _ = request.FILES
        request.POST = QueryDict()
        return super().post(request, *args, **kwargs)
