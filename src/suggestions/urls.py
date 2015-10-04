from django.conf.urls import  url
from suggestions import views

# Admin site customizations

urlpatterns = [
    url(r'^$', views.suggestion_list, name='list'),
    url(r'^new$', views.suggestion_create, name='create'),
    url(r'^edit/(?P<pk>\d+)$', views.suggestion_update, name='edit'),
    url(r'^delete/(?P<pk>\d+)$', views.suggestion_delete, name='delete'),
    url(r'^(?P<id>\d+)/comment/$', views.comment, name='comment'),
    url(r'^(?P<id>\d+)/$', views.suggestion_list, name='list'),
    url(r'^(?P<id>[0-9]+)/approve/$', views.suggestion_approve, name='approve'),
    url(r'^(?P<id>[0-9]+)/vote/(?P<vote>[0-9]+)$', views.vote, name='vote'),

]
