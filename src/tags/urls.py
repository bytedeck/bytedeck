from django.urls import path

from taggit.models import Tag
from tags.views import TagDetail, TagList
from utilities.views import ModelAutocomplete

app_name = 'tags'

urlpatterns = [
    path('', TagList.as_view(), name='list'),
    path('autocomplete/', ModelAutocomplete.as_view(model=Tag), name='autocomplete'),
    path('<int:pk>/', TagDetail.as_view(), name='detail'),
]
