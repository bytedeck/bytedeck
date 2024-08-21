from django.urls import re_path

from . import views

app_name = 'djcytoscape'
urlpatterns = [
    re_path(r'^$', views.index, name='index'),

    re_path(r'^generate/(?P<quest_id>[0-9]+)/(?P<scape_id>[0-9]+)$', views.ScapeGenerateMap.as_view(), name='generate_map'),
    re_path(r'^generate/$', views.ScapeGenerateMap.as_view(), name='generate_unseeded'),
    re_path(r'^primary/$', views.primary, name='primary'),

    re_path(r'^(?P<scape_id>[0-9]+)/$', views.quest_map, name='quest_map'),
    re_path(r'^(?P<scape_id>[0-9]+)/(?P<user_id>[0-9]+)/$', views.quest_map_personalized, name='quest_map_personalized'),
    re_path(r'^(?P<ct_id>[0-9]+)/(?P<obj_id>[0-9]+)/(?P<originating_scape_id>[0-9]+)/$', views.quest_map_interlink, name='quest_map_interlink'),
    re_path(r'^(?P<pk>[0-9]+)/edit/$', views.ScapeUpdate.as_view(), name='update'),
    re_path(r'^(?P<pk>[0-9]+)/delete/$', views.ScapeDelete.as_view(), name='delete'),
    re_path(r'^list/$', views.ScapeList.as_view(), name='list'),

    re_path(r'^(?P<scape_id>[0-9]+)/regenerate/$', views.regenerate, name='regenerate'),
    re_path(r'^all/regenerate/$', views.regenerate_all, name='regenerate_all'),
]
