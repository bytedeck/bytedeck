from django.conf.urls import url
from portfolios import views

app_name = 'portfolios'  # needed for static files to get picked up... why?
urlpatterns = [
    url(r'^$', views.PortfolioList.as_view(), name='list'),
    url(r'^create/$', views.PortfolioCreate.as_view(), name='create'),
    url(r'^(?P<user_id>[0-9]+)/$', views.detail, name='detail'),
    url(r'^detail/$', views.detail, name='current_user'),
    url(r'^(?P<uuid>[0-9a-z-]+)/$', views.public, name='public'),
    url(r'^(?P<pk>[0-9]+)/update/$', views.PortfolioUpdate.as_view(), name='update'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.edit, name='edit'),

    url(r'^(?P<user_id>[0-9]+)/create/$', views.ArtworkCreate.as_view(), name='art_create'),

    url(r'^art/create/(?P<doc_id>[0-9]+)$', views.art_add, name='art_add'),
    url(r'^art/(?P<pk>[0-9]+)/delete/$', views.ArtworkDelete.as_view(), name='art_delete'),
    url(r'^art/(?P<pk>[0-9]+)/edit/$', views.ArtworkUpdate.as_view(), name='art_update'),

    # url(r'^art/(?P<pk>[0-9]+)/$', views.art_detail, name='art_detail'),
]
