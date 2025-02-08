from django.urls import path, re_path

from badges import views

app_name = 'badges'

urlpatterns = [
    path('', views.badge_list, name='list'),
    path('list/', views.badge_list, name='badge_list'),
    path('create/', views.badge_create, name='badge_create'),
    path('<int:badge_id>/', views.detail, name='badge_detail'),  # shows assertions of current students only
    path('<int:badge_id>/all/', views.detail_all, name='badge_detail_all'),  # show assertions of all students
    re_path(r'^(?P<pk>[0-9]+)/edit/$', views.BadgeUpdate.as_view(), name='badge_update'),
    re_path(r'^(?P<pk>[0-9]+)/prereqs/edit/$', views.BadgePrereqsUpdate.as_view(), name='badge_prereqs_update'),
    re_path(r'^(?P<badge_id>[0-9]+)/copy/$', views.badge_copy, name='badge_copy'),
    re_path(r'^(?P<pk>[0-9]+)/delete/$', views.BadgeDelete.as_view(), name='badge_delete'),

    # Badge Assertions
    re_path(r'^(?P<badge_id>[0-9]+)/grant/(?P<user_id>[0-9]+)/$', views.assertion_create, name='grant'),
    re_path(r'^(?P<badge_id>[0-9]+)/grant/bulk/$', views.bulk_assertion_create, name='bulk_grant_badge'),
    path('grant/bulk/', views.bulk_assertion_create, name='bulk_grant'),
    re_path(r'^assertion/(?P<assertion_id>[0-9]+)/revoke/$', views.assertion_delete, name='revoke'),


    # Badge Types
    path('types/', views.BadgeTypeList.as_view(), name='badge_types'),
    path('types/create/', views.BadgeTypeCreate.as_view(), name='badge_type_create'),
    path('types/<int:pk>/edit', views.BadgeTypeUpdate.as_view(), name='badge_type_update'),
    path('types/<int:pk>/delete', views.BadgeTypeDelete.as_view(), name='badge_type_delete'),

    # Ajax
    path('ajax/on_show_badge_popup/', views.Ajax_OnShowBadgePopup.as_view(), name='ajax_on_show_badge_popup'),
    path('ajax/on_close_badge_popup/', views.Ajax_OnCloseBadgePopup.as_view(), name='ajax_on_close_badge_popup'),
]
