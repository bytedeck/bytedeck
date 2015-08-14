from django.conf.urls import  url

from notifications import views

urlpatterns = [
    url(r'^$', views.list, name='list'), # function based view
    url(r'^unread/$', views.list, name='unread'), # function based view
    url(r'^read/$', views.list, name='read'), # function based view
]
