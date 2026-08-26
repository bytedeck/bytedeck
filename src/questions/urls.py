from django.urls import path

from . import views


app_name = 'questions'


urlpatterns = [
    path('quest/<int:quest_id>/', views.QuestionListView.as_view(), name='list'),
    path('quest/<int:quest_id>/create/<str:question_type>/', views.QuestionCreateView.as_view(), name='create'),
    path('quest/<int:quest_id>/<int:pk>/update/', views.QuestionUpdateView.as_view(), name='update'),
    path('quest/<int:quest_id>/<int:pk>/delete/', views.QuestionDeleteView.as_view(), name='delete'),
    path('quest/<int:quest_id>/<int:pk>/move/<str:direction>/', views.QuestionMoveView.as_view(), name='move'),

    # A web-file answer is downloaded through here rather than linked at its storage URL, so
    # that HTML or SVG a student uploaded is never opened as a page in a marker's session.
    path('answer/<int:pk>/download/', views.answer_file_download, name='answer_file_download'),
]
