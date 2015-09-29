from django.conf.urls import  url
from suggestions import views

# Admin site customizations

urlpatterns = [
    url(r'^$', views.SuggestionList.as_view(), name='list'),
    url(r'^new$', views.SuggestionCreate.as_view(), name='create'),
    url(r'^edit/(?P<pk>\d+)$', views.SuggestionUpdate.as_view(), name='edit'),
    url(r'^delete/(?P<pk>\d+)$', views.SuggestionDelete.as_view(), name='delete'),
]
