from django.conf.urls import  url
from profile_manager import views

# Admin site customizations

urlpatterns = [
    url(r'^$', views.profile, name='profile'),
    # ex: /profile/25/
    # url(r'^(?P<profile_id>[0-9]+)/$', views.profile, name='profile'),
]
