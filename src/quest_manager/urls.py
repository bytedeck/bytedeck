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
from quest_manager import views

from django.conf.urls import url
from django.urls import path

app_name = 'quest_manager'

urlpatterns = [
    url(r'^$', views.quest_list, name=''),
    # url(r'^create/$', views.quest_create, name='quest_create'),

    # Ajax
    url(r'^ajax/$', views.ajax, name='ajax'),
    url(r'^ajax_flag/$', views.ajax_flag, name='ajax_flag'),
    url(r'^ajax_quest_info/(?P<quest_id>[0-9]+)/$', views.ajax_quest_info, name='ajax_quest_info'),
    url(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_root'),
    url(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_all'),
    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/$', views.ajax_submission_info, name='ajax_info_in_progress'),
    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/past/$', views.ajax_submission_info, name='ajax_info_past'),
    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/completed/$', views.ajax_submission_info,
        name='ajax_info_completed'),
    url(r'^ajax_submission_info/$', views.ajax_submission_info, name='ajax_submission_root'),
    url(r'^ajax_approval_info/$', views.ajax_approval_info, name='ajax_approval_root'),
    url(r'^ajax_approval_info/(?P<submission_id>[0-9]+)/$', views.ajax_approval_info, name='ajax_approval_info'),

    # Lists
    url(r'^list/(?P<quest_id>[0-9]+)/$', views.quest_list, name='quest_active'),
    url(r'^available/$', views.quest_list, name='quests'),
    url(r'^available/$', views.quest_list, name='available'),
    url(r'^available2/$', views.quest_list2, name='available2'),
    url(r'^available/all/$', views.quest_list, name='available_all'),
    url(r'^inprogress/$', views.quest_list, name='inprogress'),
    url(r'^completed/$', views.quest_list, name='completed'),
    url(r'^past/$', views.quest_list, name='past'),
    url(r'^drafts/$', views.quest_list, name='drafts'),

    # Approvals
    url(r'^approvals/$', views.approvals, name='approvals'),
    url(r'^approvals/submitted/$', views.approvals, name='submitted'),
    url(r'^approvals/submitted/all/$', views.approvals, name='submitted_all'),
    url(r'^approvals/returned/$', views.approvals, name='returned'),
    url(r'^approvals/approved/$', views.approvals, name='approved'),
    url(r'^approvals/skipped/$', views.approvals, name='skipped'),
    # url(r'^approvals/submitted/(?P<quest_id>[0-9]+)/$', views.approvals, name='submitted_for_quest'),  # Not used
    # url(r'^approvals/returned/(?P<quest_id>[0-9]+)/$', views.approvals, name='returned_for_quest'),  # Not used
    url(r'^approvals/approved/(?P<quest_id>[0-9]+)/$', views.approvals, name='approved_for_quest'),
    url(r'^approvals/approved/(?P<quest_id>[0-9]+)/all/$', views.approvals, name='approved_for_quest_all'),
    # url(r'^approvals/skipped/(?P<quest_id>[0-9]+)/$', views.approvals, name='skipped_for_quest'),  # Not used

    # Quests
    url(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    url(r'^create/$', views.QuestCreate.as_view(), name='quest_create'),
    url(r'^(?P<pk>[0-9]+)/edit/$', views.QuestUpdate.as_view(), name='quest_update'),
    url(r'^(?P<quest_id>[0-9]+)/copy/$', views.QuestCopy.as_view(), name='quest_copy'),
    url(r'^(?P<pk>[0-9]+)/delete/$', views.QuestDelete.as_view(), name='quest_delete'),
    url(r'^(?P<quest_id>[0-9]+)/start/$', views.start, name='start'),
    url(r'^(?P<quest_id>[0-9]+)/hide/$', views.hide, name='hide'),
    url(r'^(?P<quest_id>[0-9]+)/unhide/$', views.unhide, name='unhide'),
    url(r'^(?P<quest_id>[0-9]+)/skip/$', views.skipped, name='skip_for_quest'),

    path('<int:pk>/summary/', views.QuestSubmissionSummary.as_view(), name='summary'),

    # Submissions
    url(r'^submission/(?P<submission_id>[0-9]+)/skip/$', views.skip, name='skip'),
    url(r'^submission/(?P<submission_id>[0-9]+)/$', views.submission, name='submission'),
    url(r'^submission/(?P<submission_id>[0-9]+)/drop/$', views.drop, name='drop'),
    url(r'^submission/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),
    url(r'^submission/save/$', views.ajax_save_draft, name='ajax_save_draft'),
    url(r'^submission/(?P<submission_id>[0-9]+)/approve/$', views.approve, name='approve'),
    url(r'^submission/past/(?P<submission_id>[0-9]+)/$', views.submission, name='submission_past'),

    # Flagged submissions
    url(r'^submission/(?P<submission_id>[0-9]+)/flag/$', views.flag, name='flag'),
    url(r'^submission/(?P<submission_id>[0-9]+)/unflag/$', views.unflag, name='unflag'),
    url(r'^submission/flagged/$', views.flagged_submissions, name='flagged'),


    # url(r'^in-progress/(?P<pk>[0-9]+)/delete/$', views.SubmissionDelete.as_view(), name='sub_delete'),
]
