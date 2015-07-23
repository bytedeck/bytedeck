from django.conf.urls import  url
from announcements import views

urlpatterns = [
    url(r'^$', views.List.as_view(), name='list'),
    url(r'^create/$', views.Create.as_view(), name='create'),
    # url(r'^(?P<pk>\d+)/$', views.ProfileDetail.as_view(), name='profile_detail'),
    url(r'^(?P<pk>\d+)/delete/$', views.Delete.as_view(), name='delete'),
    url(r'^(?P<pk>\d+)/edit/$', views.Update.as_view(), name='update'),
]
