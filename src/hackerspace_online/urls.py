"""hackerspace_online URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""

from hackerspace_online import views

from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin

# Admin site customizations

admin.site.site_header = "Hackerspace Administration"
admin.site.site_title = "Hackerspace Admin"

urlpatterns = [
    url(r'^grappelli/', include('grappelli.urls')),  # grappelli URLS
    url(r'^$', views.home, name='home'),
    url(r'^a/simple/life/is/its/own/reward/', views.simple, name='simple'),
    url(r'^config/$', views.config_view, name='config'),
    # quest_manager
    url(r'^quests/', include('quest_manager.urls', namespace='quests')),
    # profile_manager
    url(r'^profiles/', include('profile_manager.urls', namespace='profiles')),
    url(r'^announcements/', include('announcements.urls', namespace='announcements')),
    url(r'^comments/', include('comments.urls', namespace='comments')),
    url(r'^notifications/', include('notifications.urls', namespace='notifications')),
    url(r'^courses/', include('courses.urls', namespace='courses')),
    url(r'^achievements/', include('badges.urls', namespace='badges')),
    url(r'^suggestions/', include('suggestions.urls', namespace='suggestions')),
    url(r'^maps/', include('djcytoscape.urls', namespace='maps')),
    url(r'^portfolios/', include('portfolios.urls', namespace='portfolios')),

    # admin
    url(r'^admin/', include(admin.site.urls)),
    # summer_note
    url(r'^summernote/', include('django_summernote.urls')),
    # allauth
    url(r'^accounts/', include('allauth.urls')),
    url(r'^pages/', include('django.contrib.flatpages.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar
    urlpatterns += [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ]
