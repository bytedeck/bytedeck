from django.conf.urls import url
from comments import views

urlpatterns = [
    url(r'^(?P<id>\d+)/thread/$', views.comment_thread, name='threads'),
    url(r'^(?P<id>\d+)/flag/$', views.flag, name='flag'),
    url(r'^(?P<id>\d+)/unflag/$', views.unflag, name='unflag'),
    url(r'^create/$', views.comment_create, name='create'),

]
