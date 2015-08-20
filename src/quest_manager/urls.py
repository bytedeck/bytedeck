"""quest_manager URL Configuration

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
from django.conf.urls import  url
from quest_manager import views

# Admin site customizations

urlpatterns = [
    url(r'^$', views.quest_list, name='quests'),
    # url(r'^email_demo/$', views.email_demo, name='email_demo'),
    # url(r'^new_quest_custom/$', views.new_quest_custom, name='new_quest_custom'),
    # url(r'^quests/$', 'quest_manager.views.quests', name='quests'),
     # ex: /quest/25/
    url(r'^create/$', views.quest_create, name='quest_create'),
    url(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    # url(r'^(?P<quest_id>[0-9]+)/edit/$', views.quest_update, name='quest_update'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.QuestUpdate.as_view(), name='quest_update'),
    url(r'^(?P<quest_id>[0-9]+)/copy/$', views.quest_copy, name='quest_copy'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.QuestDelete.as_view(), name='quest_delete'),
    url(r'^(?P<quest_id>[0-9]+)/start/$', views.start, name='start'),
    url(r'^in-progress/(?P<submission_id>[0-9]+)/$', views.submission, name='submission'),
    url(r'^in-progress/(?P<submission_id>[0-9]+)/drop/$', views.drop, name='drop'),
    url(r'^in-progress/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),
    # url(r'^in-progress/(?P<pk>[0-9]+)/delete/$', views.SubmissionDelete.as_view(), name='sub_delete'),
]
