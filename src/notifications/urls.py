from notifications import views

from django.conf.urls import url

app_name = 'notifications'

urlpatterns = [
    url(r'^$', views.list, name='list'),  # function based view
    url(r'^unread/$', views.list_unread, name='list_unread'),  # function based view
    url(r'^ajax/$', views.ajax, name='ajax'),  # function based view
    url(r'^read/(?P<id>\d+)/$', views.read, name='read'),  # function based view
    url(r'^read/all/$', views.read_all, name='read_all'),  # function based view
    url(r'^ajax/mark/read/$', views.ajax_mark_read, name='ajax_mark_read'),
    # url(r'^options/$', views.options, name='options'), # function based view
]
