"""Override `SummernoteEditor` class to use customized template file (mandatory for ByteDeck project)"""

from django.urls import path

from django_summernote.urls import urlpatterns as summernote_patterns

from .views import ByteDeckSummernoteEditor, ByteDeckSummernoteUploadAttachment

urlpatterns = [
    path(
        "editor/<id>/",
        ByteDeckSummernoteEditor.as_view(),
        name="bytedeck_summernote-editor",
    ),
    # Same path as django-summernote's own upload view, which the editor posts to: listed first, this one answers.
    path(
        "upload_attachment/",
        ByteDeckSummernoteUploadAttachment.as_view(),
        name="bytedeck_summernote-upload_attachment",
    ),
]

urlpatterns += summernote_patterns
