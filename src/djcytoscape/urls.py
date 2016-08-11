from django.conf.urls import url

from . import views

app_name = 'djcytoscape'
urlpatterns = [
    url(r'^$', views.index, name='index'),

    url(r'^generate/(?P<quest_id>[0-9]+)/(?P<scape_id>[0-9]+)$', views.generate_map, name='generate_map'),
    url(r'^generate/$', views.generate_map, name='generate_unseeded'),
    url(r'^primary/$', views.primary, name='primary'),

    url(r'^(?P<scape_id>[0-9]+)/$', views.quest_map, name='quest_map'),
    url(r'^(?P<scape_id>[0-9]+)/(?P<ct_id>[0-9]+)/(?P<obj_id>[0-9]+)/(?P<originating_scape_id>[0-9]+)/$',
        views.quest_map, name='quest_map_interlink'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.ScapeUpdate.as_view(), name='update'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.ScapeDelete.as_view(), name='delete'),

    url(r'^(?P<scape_id>[0-9]+)/regenerate/$', views.regenerate, name='regenerate'),
]
