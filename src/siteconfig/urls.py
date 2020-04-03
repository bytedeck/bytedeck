from django.urls import path

from . import views

urlpatterns = [
    # path('', views.index, name='index'),
    # path('', views.ProfileDetail.as_view(), name='profile_detail'),
    path('<int:pk>', views.SiteConfigUpdate.as_view(), name='site_config_update'),
]
