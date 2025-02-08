from comments import views

from django.urls import re_path

app_name = 'comments'

urlpatterns = [
    re_path(r'^(?P<id>\d+)/flag/$', views.flag, name='flag'),
    re_path(r'^(?P<id>\d+)/unflag/$', views.unflag, name='unflag'),
    re_path(r'^(?P<id>\d+)/delete/$', views.delete, name='delete'),
]
