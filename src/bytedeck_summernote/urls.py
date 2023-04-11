"""Override `SummernoteEditor` class to use customized template file (mandatory for ByteDeck project)"""

from django.urls import path

from django_summernote.urls import urlpatterns as summernote_patterns

from .views import ByteDeckSummernoteEditor

urlpatterns = [
    path(
        "editor/<id>/",
        ByteDeckSummernoteEditor.as_view(),
        name="bytedeck_summernote-editor",
    ),
]

urlpatterns += summernote_patterns
