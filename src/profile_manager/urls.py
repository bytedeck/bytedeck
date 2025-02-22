from django.urls import re_path, path

from profile_manager import views

# For TemplateView example
# from django.views.generic import TemplateView

# Admin site customizations

app_name = 'profile_manager'

urlpatterns = [
    re_path(r'^list/all/$', views.ProfileList.as_view(), name='profile_list'),
    re_path(r'^list/current/$', views.ProfileListCurrent.as_view(), name='profile_list_current'),
    re_path(r'^list/block/(?P<pk>[0-9]+)/$', views.ProfileListBlock.as_view(), name='profile_list_block'),
    re_path(r'^list/staff/$', views.ProfileListStaff.as_view(), name='profile_list_staff'),
    re_path(r'^list/inactive/$', views.ProfileListInactive.as_view(), name='profile_list_inactive'),
    re_path(r'^tour/$', views.tour_complete, name='tour_complete'),
    re_path(r'^recalculate/current/$', views.recalculate_current_xp, name='recalculate_xp_current'),
    re_path(r'^(?P<pk>[0-9]+)/$', views.ProfileDetail.as_view(), name='profile_detail'),
    re_path(r'^(?P<profile_id>[0-9]+)/xp_toggle/$', views.xp_toggle, name='xp_toggle'),
    re_path(r'^(?P<profile_id>[0-9]+)/comment_ban_toggle/$', views.comment_ban_toggle, name='comment_ban_toggle'),
    re_path(r'^(?P<profile_id>[0-9]+)/comment_ban/$', views.comment_ban, name='comment_ban'),
    re_path(r'^(?P<pk>[0-9]+)/edit/$', views.ProfileUpdate.as_view(), name='profile_update'),
    re_path(r'^(?P<pk>[0-9]+)/delete/$', views.ProfileDelete.as_view(), name='profile_delete'),
    re_path(r'^edit/own/$', views.ProfileUpdateOwn.as_view(), name='profile_edit_own'),
    path('chart/<pk>/', views.TagChart.as_view(), name='tag_chart'),

    path('oauth-merge-account/', views.oauth_merge_account, name='oauth_merge_account'),
    path('password/change/<int:pk>/', views.PasswordReset.as_view(), name='change_password'),
    path('<pk>/resend-email-verification/', views.ProfileResendEmailVerification.as_view(), name='profile_resend_email_verification'),

    # Examples
    # Template View Example
    # re_path(r'^example/$', TemplateView.as_view(template_name='example.html'), name='example'),
    # Function based view example, same as above
    # re_path(r'^example/$', 'views.example', name='example'),
    # ex: /profile/25/
    # re_path(r'^(?P<profile_id>[0-9]+)/$', views.profile, name='profile'),
]
