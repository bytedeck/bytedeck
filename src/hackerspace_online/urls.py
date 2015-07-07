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
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin

urlpatterns = [
    #allauth
    url(r'^accounts/', include('allauth.urls')),
    #hackerspace_online
    url(r'^profile/$', 'hackerspace_online.views.profile',
            name='profile'),
    url(r'^announcements/$', 'hackerspace_online.views.announcements',
        name='announcements'),
    url(r'^quests/$', 'hackerspace_online.views.quests',
        name='quests'),
    url(r'^achievements/$', 'hackerspace_online.views.achievements',
        name='achievements'),
    url(r'^$', 'quest_manager.views.home',
        name='home'),
    #quest_manager
    url(r'^email_demo/$', 'quest_manager.views.email_demo',
        name='email_demo'),
    url(r'^new_quest_custom/$', 'quest_manager.views.new_quest_custom',
        name='new_quest_custom'),
    #admin
    url(r'^admin/', include(admin.site.urls),
        name='django-admin'),

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
