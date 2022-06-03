from django.conf.urls import url
from django.urls import path

from utilities import views

app_name = 'utilities'

urlpatterns = [
    # url(r'^$', views.suggestion_list, name='list'),
    url(r'^videos/$', views.videos, name='videos'),

    # flatpages
    path('custom-pages/', views.FlatPageListView.as_view(), name='flatpage_list'),
    path('custom-pages/create/', views.FlatPageCreateView.as_view(), name='flatpage_create'),
    path('custom-pages/edit/<int:pk>/', views.FlatPageUpdateView.as_view(), name='flatpage_edit'),
    path('custom-pages/delete/<int:pk>/', views.FlatPageDeleteView.as_view(), name='flatpage_delete'),
]
