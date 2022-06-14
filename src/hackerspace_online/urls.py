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
from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include

from badges.views import AchievementRedirectView
from hackerspace_online import views
from siteconfig.models import SiteConfig

admin.site.site_header = lambda: SiteConfig.get().site_name
admin.site.site_title = lambda: SiteConfig.get().site_name_short

app_name = 'hackerspace_online'

urlpatterns = [
    url(r'^grappelli/', include('grappelli.urls')),
    url(r'^admin/', admin.site.urls)
]

urlpatterns += [
    url(r'^$', views.home, name='home'),
    url(r'^a/simple/life/is/its/own/reward/', views.simple, name='simple'),
    # quest_manager
    url(r'^quests/', include('quest_manager.urls', namespace='quests')),
    # profile_manager
    url(r'^profiles/', include('profile_manager.urls', namespace='profiles')),
    url(r'^announcements/', include('announcements.urls', namespace='announcements')),
    url(r'^comments/', include('comments.urls', namespace='comments')),
    url(r'^notifications/', include('notifications.urls', namespace='notifications')),
    url(r'^courses/', include('courses.urls', namespace='courses')),
    url(r'^achievements/', AchievementRedirectView.as_view()),
    url(r'^badges/', include('badges.urls', namespace='badges')),
    url(r'^maps/', include('djcytoscape.urls', namespace='maps')),
    url(r'^portfolios/', include('portfolios.urls', namespace='portfolios')),
    url(r'^utilities/', include('utilities.urls', namespace='utilities')),
    url(r'^config/', include('siteconfig.urls', namespace='config')),
    url(r'^decks/', include('tenant.urls', namespace='decks')),

    # summer_note
    url(r'^summernote/', include('django_summernote.urls')),
    # allauth
    url(r'^accounts/password/reset/$',
        views.CustomPasswordResetView.as_view(),
        name='account_reset_password'),
    url(r'^accounts/password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$',
        views.CustomPasswordResetFromKeyView.as_view(),
        name='account_reset_password_from_key'),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^pages/', include('django.contrib.flatpages.urls')),
    # select2
    url(r'^select2/', include('django_select2.urls')),
    # Browsers looks for favicon.ico at root, redirect them to proper favicon to prevent constant 404s
    url(r'^favicon\.ico$', views.FaviconRedirectView.as_view()),
]


if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    import debug_toolbar

    urlpatterns += [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ]
