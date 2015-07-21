from django.conf.urls import  url
from announcements import views

urlpatterns = [
    url(r'^$', views.List.as_view(), name='profile_list'),
    # url(r'^create/$', views.ProfileCreate.as_view(), name='profile_create'),
    # url(r'^(?P<pk>\d+)/$', views.ProfileDetail.as_view(), name='profile_detail'),
    # url(r'^(?P<pk>\d+)/edit/$', views.ProfileUpdate.as_view(), name='profile_update'),
]
