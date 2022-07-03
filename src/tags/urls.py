from django.urls import path

from tags import views

app_name = 'tags'

urlpatterns = [
    path('autocomplete/', views.TagAutocomplete.as_view(), name='autocomplete'),
]
