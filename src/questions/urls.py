from django.urls import path
from . import views


app_name = 'questions'


urlpatterns = [
    path('<int:quest_id>/list/', views.QuestionListView.as_view(), name='list'),
    path('<int:quest_id>/questions/create/<str:question_type>', views.QuestionCreateView.as_view(),
         name='create'),
    path('<int:quest_id>/questions/<int:pk>/', views.QuestionUpdateView.as_view(), name='update'),
    path('<int:quest_id>/questions/<int:pk>/delete/', views.QuestionDeleteView.as_view(), name='delete'),
]
