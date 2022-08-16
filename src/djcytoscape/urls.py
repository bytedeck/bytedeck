from django.conf.urls import url

from . import views

app_name = 'djcytoscape'
urlpatterns = [
    url(r'^$', views.index, name='index'),

    url(r'^generate/(?P<quest_id>[0-9]+)/(?P<scape_id>[0-9]+)$', views.ScapeGenerateMap.as_view(), name='generate_map'),
    url(r'^generate/$', views.ScapeGenerateMap.as_view(), name='generate_unseeded'),
    url(r'^primary/$', views.primary, name='primary'),

    url(r'^(?P<scape_id>[0-9]+)/$', views.quest_map, name='quest_map'),
    url(r'^(?P<scape_id>[0-9]+)/(?P<user_id>[0-9]+)/$', views.quest_map_personalized, name='quest_map_personalized'),
    url(r'^(?P<ct_id>[0-9]+)/(?P<obj_id>[0-9]+)/(?P<originating_scape_id>[0-9]+)/$',
        views.quest_map_interlink, name='quest_map_interlink'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.ScapeUpdate.as_view(), name='update'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.ScapeDelete.as_view(), name='delete'),
    url(r'^list/$', views.ScapeList.as_view(), name='list'),

    url(r'^(?P<scape_id>[0-9]+)/regenerate/$', views.regenerate, name='regenerate'),
    url(r'^all/regenerate/$', views.regenerate_all, name='regenerate_all'),
]
