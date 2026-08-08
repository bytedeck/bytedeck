from django.urls import path

from . import views


app_name = 'questions'


urlpatterns = [
    path('quest/<int:quest_id>/', views.QuestionListView.as_view(), name='list'),
    path('quest/<int:quest_id>/create/<str:question_type>/', views.QuestionCreateView.as_view(), name='create'),
    path('quest/<int:quest_id>/<int:pk>/update/', views.QuestionUpdateView.as_view(), name='update'),
    path('quest/<int:quest_id>/<int:pk>/delete/', views.QuestionDeleteView.as_view(), name='delete'),
]
