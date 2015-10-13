from django.conf.urls import  url
from announcements import views

urlpatterns = [
    url(r'^$', views.list, name='list'), # function based view
    # url(r'^$', views.List.as_view(), name='list'), # CBV
    # url(r'^create/$', views.create, name='create'),
    url(r'^create/$', views.Create.as_view(), name='create'), #CBV
    url(r'^(?P<pk>\d+)/delete/$', views.Delete.as_view(), name='delete'),
    url(r'^(?P<pk>\d+)/edit/$', views.Update.as_view(), name='update'),
    url(r'^(?P<id>\d+)/copy/$', views.copy, name='copy'),
    url(r'^(?P<id>\d+)/publish/$', views.publish, name='publish'),
    url(r'^(?P<id>\d+)/comment/$', views.comment, name='comment'),
    url(r'^(?P<id>\d+)/$', views.list, name='list'),

]
