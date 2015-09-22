from django.conf.urls import  url
from profile_manager import views

#For TemplateView example
# from django.views.generic import TemplateView

# Admin site customizations

urlpatterns = [
    url(r'^$', views.ProfileList.as_view(), name='profile_list'),
    url(r'^create/$', views.ProfileCreate.as_view(), name='profile_create'),
    url(r'^tour/$', views.tour_complete, name='tour_complete'),
    # url(r'^edit/$', views.ProfileUpdate.as_view(), name='profile_update'),
    # url(r'^detail/$', views.ProfileDetail.as_view(), name='profile_detail'),
    url(r'^(?P<pk>[0-9]+)/$', views.ProfileDetail.as_view(), name='profile_detail'),
    url(r'^(?P<profile_id>[0-9]+)/GameLab$', views.GameLab_toggle, name='GameLab_toggle'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.ProfileUpdate.as_view(), name='profile_update'),
    # url(r'^edit/(?P<pk>[0-9]+)/$', views.ProfileEdit.as_view(), name='profile_edit'),



    #Examples
    #Template View Example
    #url(r'^example/$', TemplateView.as_view(template_name='example.html'), name='example'),
    #Function based view example, same as above
    # url(r'^example/$', 'views.example', name='example'),
    # ex: /profile/25/
    # url(r'^(?P<profile_id>[0-9]+)/$', views.profile, name='profile'),
]
