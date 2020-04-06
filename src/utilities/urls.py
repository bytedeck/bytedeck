from django.conf.urls import url

from utilities import views

app_name = 'utilities'

urlpatterns = [
    # url(r'^$', views.suggestion_list, name='list'),
    url(r'^videos/$', views.videos, name='videos'),

]
