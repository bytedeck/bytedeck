from django.urls import path

from badges import views

from django.conf.urls import url

from badges.models import Badge
from utilities.views import ModelAutocomplete

app_name = 'badges'

urlpatterns = [
    path('', views.badge_list, name='list'),
    path('list/', views.badge_list, name='badge_list'),
    path('create/', views.badge_create, name='badge_create'),
    path('<int:badge_id>', views.detail, name='badge_detail'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.BadgeUpdate.as_view(), name='badge_update'),
    url(r'^(?P<pk>[0-9]+)/prereqs/edit/$', views.BadgePrereqsUpdate.as_view(), name='badge_prereqs_update'),
    url(r'^(?P<badge_id>[0-9]+)/copy/$', views.badge_copy, name='badge_copy'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.BadgeDelete.as_view(), name='badge_delete'),
    path('autocomplete/', ModelAutocomplete.as_view(model=Badge), name='badge_autocomplete'),

    # Badge Assertions
    url(r'^(?P<badge_id>[0-9]+)/grant/(?P<user_id>[0-9]+)/$', views.assertion_create, name='grant'),
    url(r'^(?P<badge_id>[0-9]+)/grant/bulk/$', views.bulk_assertion_create, name='bulk_grant_badge'),
    path('grant/bulk/', views.bulk_assertion_create, name='bulk_grant'),
    url(r'^assertion/(?P<assertion_id>[0-9]+)/revoke/$', views.assertion_delete, name='revoke'),


    # Badge Types
    path('types/', views.BadgeTypeList.as_view(), name='badge_types'),
    path('types/create/', views.BadgeTypeCreate.as_view(), name='badge_type_create'),
    path('types/<int:pk>/edit', views.BadgeTypeUpdate.as_view(), name='badge_type_update'),
    path('types/<int:pk>/delete', views.BadgeTypeDelete.as_view(), name='badge_type_delete'),
]
