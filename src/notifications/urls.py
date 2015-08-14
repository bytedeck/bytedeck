from django.conf.urls import  url

from notifications import views

urlpatterns = [
    url(r'^$', views.list, name='list'), # function based view
    url(r'^ajax/$', views.ajax, name='ajax'), # function based view
    url(r'^read/(?P<id>\d+)/$', views.read, name='read'), # function based view

]
