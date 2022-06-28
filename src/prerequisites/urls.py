from django.urls import path

from prerequisites import views
from prerequisites.forms import PrereqFormInline

# app_name = 'prerequisites' # django-autocomplete-light doesn't work (by default anyway) with namespaces

urlpatterns = [
    path('autocomplete/ct/', views.PrereqContentTypeAutocomplete.as_view(), name='prereq-ct-autocomplete'),
]

#  https://django-autocomplete-light.readthedocs.io/en/master/gfk.html#register-the-view-for-the-form
urlpatterns.extend(PrereqFormInline.as_urls())
