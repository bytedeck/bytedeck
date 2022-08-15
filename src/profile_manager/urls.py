from django.conf.urls import url
from django.urls import path

from profile_manager import views

# For TemplateView example
# from django.views.generic import TemplateView

# Admin site customizations

app_name = 'profile_manager'

urlpatterns = [
    url(r'^list/all/$', views.ProfileList.as_view(), name='profile_list'),
    url(r'^list/current/$', views.ProfileListCurrent.as_view(), name='profile_list_current'),
    url(r'^list/staff/$', views.ProfileListStaff.as_view(), name='profile_list_staff'),
    url(r'^list/inactive/$', views.ProfileListInactive.as_view(), name='profile_list_inactive'),
    url(r'^tour/$', views.tour_complete, name='tour_complete'),
    url(r'^recalculate/current/$', views.recalculate_current_xp, name='recalculate_xp_current'),
    url(r'^(?P<pk>[0-9]+)/$', views.ProfileDetail.as_view(), name='profile_detail'),
    url(r'^(?P<profile_id>[0-9]+)/xp_toggle/$', views.xp_toggle, name='xp_toggle'),
    url(r'^(?P<profile_id>[0-9]+)/comment_ban_toggle/$', views.comment_ban_toggle, name='comment_ban_toggle'),
    url(r'^(?P<profile_id>[0-9]+)/comment_ban/$', views.comment_ban, name='comment_ban'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.ProfileUpdate.as_view(), name='profile_update'),
    url(r'^edit/own/$', views.ProfileUpdateOwn.as_view(), name='profile_edit_own'),

    path('password/change/<int:pk>/', views.PasswordReset.as_view(), name='change_password'),

    # Examples
    # Template View Example
    # url(r'^example/$', TemplateView.as_view(template_name='example.html'), name='example'),
    # Function based view example, same as above
    # url(r'^example/$', 'views.example', name='example'),
    # ex: /profile/25/
    # url(r'^(?P<profile_id>[0-9]+)/$', views.profile, name='profile'),
]
