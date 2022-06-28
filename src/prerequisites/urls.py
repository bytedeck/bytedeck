from prerequisites.forms import PrereqFormInline

# app_name = 'prerequisites' # django-autocomplete-light doesn't work (by default anyway) with namespaces

urlpatterns = []

#  https://django-autocomplete-light.readthedocs.io/en/master/gfk.html#register-the-view-for-the-form
urlpatterns.extend(PrereqFormInline.as_urls())
