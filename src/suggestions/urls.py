from suggestions import views

from django.conf.urls import url

# Admin site customizations

urlpatterns = [
    url(r'^$', views.suggestion_list, name='list'),
    url(r'^active/$', views.suggestion_list, name='list_active'),
    url(r'^completed/$', views.suggestion_list_completed, name='list_completed'),
    url(r'^new/$', views.suggestion_create, name='create'),
    url(r'^edit/(?P<pk>\d+)/$', views.suggestion_update, name='edit'),
    url(r'^(?P<pk>\d+)/delete/$', views.suggestion_delete, name='delete'),
    url(r'^(?P<pk>\d+)/reject/$', views.suggestion_reject, name='reject'),
    url(r'^(?P<pk>\d+)/complete/$', views.suggestion_complete, name='complete'),
    url(r'^(?P<id>\d+)/comment/$', views.comment, name='comment'),
    url(r'^(?P<id>\d+)/$', views.suggestion_list, name='list'),
    url(r'^(?P<id>[0-9]+)/approve/$', views.suggestion_approve, name='approve'),
    url(r'^vote/(?P<id>[0-9]+)/upvote/$', views.up_vote, name='upvote'),
    url(r'^vote/(?P<id>[0-9]+)/downvote/$', views.down_vote, name='downvote'),

]
