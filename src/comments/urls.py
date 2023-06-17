from comments import views

from django.conf.urls import url

app_name = 'comments'

urlpatterns = [
    # url(r'^(?P<id>\d+)/thread/$', views.comment_thread, name='threads'),
    url(r'^(?P<id>\d+)/flag/$', views.flag, name='flag'),
    url(r'^(?P<id>\d+)/unflag/$', views.unflag, name='unflag'),
    url(r'^(?P<id>\d+)/delete/$', views.delete, name='delete'),
    # url(r'^create/$', views.comment_create, name='create'),

]
