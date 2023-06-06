from django.conf.urls import url
from portfolios import views

app_name = 'portfolios'

urlpatterns = [
    url(r'^$', views.PortfolioList.as_view(), name='list'),
    url(r'^public/$', views.public_list, name='public_list'),
    url(r'^(?P<pk>[0-9]+)/$', views.PortfolioDetail.as_view(), name='detail'),
    url(r'^detail/$', views.PortfolioDetail.as_view(), name='current_user'),
    url(r'^(?P<uuid>[0-9a-z-]+)/$', views.public, name='public'),
    # url(r'^(?P<pk>[0-9]+)/update/$', views.PortfolioUpdate.as_view(), name='update'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.edit, name='edit'),

    # adding art via portfolio form
    url(r'^art/(?P<pk>[0-9]+)/create/$', views.ArtworkCreate.as_view(), name='art_create'),

    # adding art from a file in a quest comment
    url(r'^art/create/(?P<doc_id>[0-9]+)$', views.art_add, name='art_add'),
    url(r'^art/(?P<pk>[0-9]+)/delete/$', views.ArtworkDelete.as_view(), name='art_delete'),
    url(r'^art/(?P<pk>[0-9]+)/edit/$', views.ArtworkUpdate.as_view(), name='art_update'),

    # url(r'^art/(?P<pk>[0-9]+)/$', views.art_detail, name='art_detail'),
]
