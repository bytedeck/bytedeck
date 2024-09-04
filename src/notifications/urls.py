from notifications import views

from django.urls import re_path

app_name = 'notifications'

urlpatterns = [
    re_path(r'^$', views.list, name='list'),  # function based view
    re_path(r'^unread/$', views.list_unread, name='list_unread'),  # function based view
    re_path(r'^read/(?P<id>\d+)/$', views.read, name='read'),  # function based view
    re_path(r'^read/all/$', views.read_all, name='read_all'),  # function based view
    re_path(r'^ajax/$', views.ajax, name='ajax'),  # function based view
    re_path(r'^ajax/mark/read/$', views.ajax_mark_read, name='ajax_mark_read'),  # function based view
]
