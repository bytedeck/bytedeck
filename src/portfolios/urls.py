from django.urls import re_path
from portfolios import views

app_name = 'portfolios'

urlpatterns = [
    re_path(r'^$', views.PortfolioList.as_view(), name='list'),
    re_path(r'^public/$', views.public_list, name='public_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', views.PortfolioDetail.as_view(), name='detail'),
    re_path(r'^detail/$', views.PortfolioDetail.as_view(), name='current_user'),
    re_path(r'^(?P<uuid>[0-9a-z-]+)/$', views.public, name='public'),
    re_path(r'^(?P<pk>[0-9]+)/edit/$', views.PortfolioUpdate.as_view(), name='edit'),

    # adding art via portfolio form
    re_path(r'^art/(?P<pk>[0-9]+)/create/$', views.ArtworkCreate.as_view(), name='art_create'),

    # adding art from a file in a quest comment
    re_path(r'^art/create/(?P<doc_id>[0-9]+)$', views.art_add, name='art_add'),
    re_path(r'^art/(?P<pk>[0-9]+)/delete/$', views.ArtworkDelete.as_view(), name='art_delete'),
    re_path(r'^art/(?P<pk>[0-9]+)/edit/$', views.ArtworkUpdate.as_view(), name='art_update'),
]
