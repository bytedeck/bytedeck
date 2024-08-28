from announcements import views

from django.urls import re_path

app_name = 'announcements'

urlpatterns = [
    re_path(r'^$', views.list, name='list'),  # function based view
    re_path(r'^archived/$', views.list, name='archived'),
    # url(r'^$', views.List.as_view(), name='list'),  # CBV
    # url(r'^create/$', views.create, name='create'),
    re_path(r'^create/$', views.Create.as_view(), name='create'),  # CBV
    re_path(r'^(?P<pk>\d+)/delete/$', views.Delete.as_view(), name='delete'),
    re_path(r'^(?P<pk>\d+)/edit/$', views.Update.as_view(), name='update'),
    re_path(r'^(?P<ann_id>\d+)/copy/$', views.copy, name='copy'),
    re_path(r'^(?P<ann_id>\d+)/publish/$', views.publish, name='publish'),
    re_path(r'^(?P<ann_id>\d+)/comment/$', views.comment, name='comment'),
    re_path(r'^(?P<ann_id>\d+)/$', views.list, name='list'),

]
