from django.conf.urls import  url
from badges import views

urlpatterns = [
    url(r'^$', views.list, name='list'),
    url(r'^create/$', views.badge_create, name='badge_create'),
    url(r'^(?P<badge_id>[0-9]+)/$', views.detail, name='badge_detail'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.BadgeUpdate.as_view(), name='badge_update'),
    url(r'^(?P<badge_id>[0-9]+)/copy/$', views.badge_copy, name='badge_copy'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.BadgeDelete.as_view(), name='badge_delete'),

]
