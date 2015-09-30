from django.conf.urls import  url
from suggestions import views

# Admin site customizations

urlpatterns = [
    url(r'^$', views.suggestion_list, name='list'),
    url(r'^new$', views.suggestion_create, name='create'),
    url(r'^edit/(?P<pk>\d+)$', views.suggestion_update, name='edit'),
    url(r'^delete/(?P<pk>\d+)$', views.suggestion_delete, name='delete'),
    # url(r'^$', views.SuggestionList.as_view(), name='list'),
    # url(r'^new$', views.SuggestionCreate.as_view(), name='create'),
    # url(r'^edit/(?P<pk>\d+)$', views.SuggestionUpdate.as_view(), name='edit'),
    # url(r'^delete/(?P<pk>\d+)$', views.SuggestionDelete.as_view(), name='delete'),
]
