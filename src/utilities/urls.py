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

    # menu items
    path('menuitem/', views.MenuItemList.as_view(), name='menu_items'),
    path('menuitem/create/', views.MenuItemCreate.as_view(), name='menu_item_create'),
    path('menuitem/edit/<int:pk>/', views.MenuItemUpdate.as_view(), name='menu_item_update'),
    path('menuitem/delete/<int:pk>/', views.MenuItemDelete.as_view(), name='menu_item_delete'),
]
