from utilities import views

from django.conf.urls import url

# Admin site customizations

app_name = 'utilities'

urlpatterns = [
    # url(r'^$', views.suggestion_list, name='list'),
    url(r'^videos/$', views.videos, name='videos'),


]
