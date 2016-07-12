from suggestions import views

from django.conf.urls import url

# Admin site customizations

urlpatterns = [
    url(r'^$', views.suggestion_list, name='list'),
    url(r'^new/$', views.suggestion_create, name='create'),
    url(r'^edit/(?P<pk>\d+)/$', views.suggestion_update, name='edit'),
    url(r'^delete/(?P<pk>\d+)/$', views.suggestion_delete, name='delete'),
    url(r'^(?P<id>\d+)/comment/$', views.comment, name='comment'),
    url(r'^(?P<id>\d+)/$', views.suggestion_list, name='list'),
    url(r'^(?P<id>[0-9]+)/approve/$', views.suggestion_approve, name='approve'),
    url(r'^(?P<id>[0-9]+)/upvote/$', views.vote, name='upvote'),
    url(r'^(?P<id>[0-9]+)/downvote/$', views.vote, name='downvote'),

]
