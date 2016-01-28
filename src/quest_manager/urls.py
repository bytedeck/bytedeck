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
    url(r'^ajax/$', views.ajax, name='ajax'),
    url(r'^list/(?P<quest_id>[0-9]+)/$', views.quest_list, name='quest_active'),
    url(r'^list/submission/(?P<submission_id>[0-9]+)/$', views.quest_list, name='submission_active'),
    url(r'^available/$', views.quest_list, name='available'),
    url(r'^inprogress/$', views.quest_list, name='inprogress'),
    url(r'^completed/$', views.quest_list, name='completed'),
    url(r'^past/$', views.quest_list, name='past'),
    url(r'^approvals/$', views.approvals, name='approvals'),
    url(r'^approvals/submitted/$', views.approvals, name='submitted'),
    url(r'^approvals/returned/$', views.approvals, name='returned'),
    url(r'^approvals/approved/$', views.approvals, name='approved'),
    url(r'^approvals/gamelab/$', views.approvals, name='gamelab'),
    url(r'^create/$', views.quest_create, name='quest_create'),
    url(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    url(r'^(?P<quest_id>[0-9]+)/submitted/$', views.submissions, name='submitted_for_quest'),
    url(r'^(?P<quest_id>[0-9]+)/returned/$', views.submissions, name='returned_for_quest'),
    url(r'^(?P<quest_id>[0-9]+)/approved/$', views.submissions, name='approved_for_quest'),
    url(r'^(?P<quest_id>[0-9]+)/gamelab/$', views.submissions, name='gamelab_for_quest'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.QuestUpdate.as_view(), name='quest_update'),
    url(r'^(?P<quest_id>[0-9]+)/copy/$', views.quest_copy, name='quest_copy'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.QuestDelete.as_view(), name='quest_delete'),
    url(r'^(?P<quest_id>[0-9]+)/start/$', views.start, name='start'),
    url(r'^(?P<quest_id>[0-9]+)/gamelabtransfer/$', views.gamelabtransfer, name='gamelabtransfer'),
    url(r'^submission/(?P<submission_id>[0-9]+)/skip/$', views.skip, name='skip'),
    url(r'^submission/(?P<submission_id>[0-9]+)/$', views.submission, name='submission'),
    url(r'^submission/(?P<submission_id>[0-9]+)/drop/$', views.drop, name='drop'),
    url(r'^submission/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),
    url(r'^submission/(?P<submission_id>[0-9]+)/approve/$', views.approve, name='approve'),

    # url(r'^in-progress/(?P<pk>[0-9]+)/delete/$', views.SubmissionDelete.as_view(), name='sub_delete'),
]
