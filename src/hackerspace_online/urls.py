"""hackerspace_online URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  re_path(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  re_path(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  re_path(r'^blog/', include(blog_urls))
"""
from django.conf import settings
from django.urls import re_path
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include

from decorator_include import decorator_include

from badges.views import AchievementRedirectView
from hackerspace_online import views
from siteconfig.models import SiteConfig
from tenant.views import non_public_only_view

admin.site.site_header = lambda: SiteConfig.get().site_name
admin.site.site_title = lambda: SiteConfig.get().site_name_short

app_name = 'hackerspace_online'

urlpatterns = [
    re_path(r'^grappelli/', include('grappelli.urls')),
    re_path(r'^admin/', admin.site.urls)
]

urlpatterns += [
    re_path(r'^$', views.home, name='home'),
    re_path(r'^a/simple/life/is/its/own/reward/', views.simple, name='simple'),
    # quest_manager
    url(r'^library/', include('library.urls', namespace='library')),
    url(r'^quests/', include('quest_manager.urls', namespace='quests')),
    # questions
    url(r'^questions/', include('questions.urls')),
    # profile_manager
    re_path(r'^profiles/', include('profile_manager.urls', namespace='profiles')),
    re_path(r'^announcements/', include('announcements.urls', namespace='announcements')),
    re_path(r'^comments/', include('comments.urls', namespace='comments')),
    re_path(r'^notifications/', include('notifications.urls', namespace='notifications')),
    re_path(r'^courses/', include('courses.urls', namespace='courses')),
    re_path(r'^achievements/', AchievementRedirectView.as_view()),
    re_path(r'^badges/', include('badges.urls', namespace='badges')),
    re_path(r'^maps/', include('djcytoscape.urls', namespace='maps')),
    re_path(r'^portfolios/', include('portfolios.urls', namespace='portfolios')),
    re_path(r'^utilities/', include('utilities.urls', namespace='utilities')),
    re_path(r'^config/', include('siteconfig.urls', namespace='config')),
    re_path(r'^decks/', include('tenant.urls', namespace='decks')),
    # bytedeck summernote
    re_path(r'^summernote/', include('bytedeck_summernote.urls')),

    re_path(r'^tags/', include('tags.urls', namespace='tags')),

    # allauth
    re_path(r'^accounts/password/reset/$', views.CustomPasswordResetView.as_view(), name='account_reset_password'),
    re_path(r'^accounts/password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$',
            views.CustomPasswordResetFromKeyView.as_view(), name='account_reset_password_from_key'),
    # apply `non_public_only_view` decorator on all `allauth` views, fix #1214
    re_path(r'^accounts/', decorator_include(non_public_only_view, "allauth.urls")),
    re_path(r'^pages/', include('django.contrib.flatpages.urls')),

    # select2
    re_path(r'^select2/', include('django_select2.urls')),
    # Browsers looks for favicon.ico at root, redirect them to proper favicon to prevent constant 404s
    re_path(r'^favicon\.ico$', views.FaviconRedirectView.as_view()),
]


if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    import debug_toolbar

    urlpatterns += [
        re_path(r'^__debug__/', include(debug_toolbar.urls)),
    ]
