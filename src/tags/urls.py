from django.urls import path

from taggit.models import Tag

from tags import views
from utilities.views import ModelAutocomplete

app_name = 'tags'

urlpatterns = [
    path('autocomplete/', ModelAutocomplete.as_view(model=Tag), name='autocomplete'),

    path('', views.TagList.as_view(), name='list'),
    path('create/', views.TagCreate.as_view(), name='create'),
    path('<int:pk>/', views.TagDetailStaff.as_view(), name='detail_staff'),
    path('<int:tag_pk>/<int:user_pk>/', views.TagDetailStudent.as_view(), name='detail_student'),
    path('update/<int:pk>/', views.TagUpdate.as_view(), name='update'),
    path('delete/<int:pk>/', views.TagDelete.as_view(), name='delete'),
]
