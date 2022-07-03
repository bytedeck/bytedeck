from django.urls import path

from taggit.models import Tag
from utilities.views import ModelAutocomplete

app_name = 'tags'

urlpatterns = [
    path('autocomplete/', ModelAutocomplete.as_view(model=Tag), name='autocomplete'),
]
