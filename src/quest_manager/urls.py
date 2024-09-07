"""quest_manager URL Configuration

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

from quest_manager import views

from django.urls import re_path, path

app_name = 'quest_manager'

urlpatterns = [
    re_path(r'^$', views.quest_list, name=''),

    # Ajax
    re_path(r'^ajax/$', views.ajax_submission_count, name='ajax_submission_count'),
    re_path(r'^ajax_flag/$', views.ajax_flag, name='ajax_flag'),
    re_path(r'^ajax_quest_info/(?P<quest_id>[0-9]+)/$', views.ajax_quest_info, name='ajax_quest_info'),
    re_path(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_root'),
    re_path(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_all'),
    re_path(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/$', views.ajax_submission_info, name='ajax_info_in_progress'),
    re_path(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/past/$', views.ajax_submission_info, name='ajax_info_past'),
    re_path(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/completed/$', views.ajax_submission_info, name='ajax_info_completed'),
    re_path(r'^ajax_submission_info/$', views.ajax_submission_info, name='ajax_submission_root'),
    re_path(r'^ajax_submission_approve/(?P<submission_id>[0-9]+)/approve/$', views.ApproveView.as_view(), name='ajax_approve'),
    re_path(r'^ajax_approval_info/$', views.ajax_approval_info, name='ajax_approval_root'),
    re_path(r'^ajax_approval_info/(?P<submission_id>[0-9]+)/$', views.ajax_approval_info, name='ajax_approval_info'),

    # Lists
    re_path(r'^list/(?P<quest_id>[0-9]+)/$', views.quest_list, name='quest_active'),
    re_path(r'^available/$', views.quest_list, name='quests'),
    re_path(r'^available/$', views.quest_list, name='available'),
    re_path(r'^available/all/$', views.quest_list, name='available_all'),
    re_path(r'^inprogress/$', views.quest_list, name='inprogress'),
    re_path(r'^completed/$', views.quest_list, name='completed'),
    re_path(r'^past/$', views.quest_list, name='past'),
    re_path(r'^drafts/$', views.quest_list, name='drafts'),

    # Approvals
    re_path(r'^approvals/$', views.approvals, name='approvals'),
    re_path(r'^approvals/submitted/$', views.approvals, name='submitted'),
    re_path(r'^approvals/submitted/all/$', views.approvals, name='submitted_all'),
    re_path(r'^approvals/returned/$', views.approvals, name='returned'),
    re_path(r'^approvals/approved/$', views.approvals, name='approved'),
    re_path(r'^approvals/flagged/$', views.approvals, name='flagged'),
    re_path(r'^approvals/approved/(?P<quest_id>[0-9]+)/$', views.approvals, name='approved_for_quest'),
    re_path(r'^approvals/approved/(?P<quest_id>[0-9]+)/all/$', views.approvals, name='approved_for_quest_all'),

    # Quests
    re_path(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    re_path(r'^create/$', views.QuestCreate.as_view(), name='quest_create'),
    re_path(r'^(?P<pk>[0-9]+)/edit/$', views.QuestUpdate.as_view(), name='quest_update'),
    re_path(r'^(?P<pk>[0-9]+)/prereqs/edit/$', views.QuestPrereqsUpdate.as_view(), name='quest_prereqs_update'),
    re_path(r'^(?P<quest_id>[0-9]+)/copy/$', views.QuestCopy.as_view(), name='quest_copy'),
    re_path(r'^(?P<pk>[0-9]+)/delete/$', views.QuestDelete.as_view(), name='quest_delete'),
    re_path(r'^(?P<pk>[0-9]+)/share/$', views.QuestShare.as_view(), name='quest_share'),
    re_path(r'^(?P<quest_id>[0-9]+)/start/$', views.start, name='start'),
    re_path(r'^(?P<quest_id>[0-9]+)/hide/$', views.hide, name='hide'),
    re_path(r'^(?P<quest_id>[0-9]+)/unhide/$', views.unhide, name='unhide'),
    re_path(r'^(?P<quest_id>[0-9]+)/skip/$', views.skipped, name='skip_for_quest'),

    # Quest/Submission Summary Metrics
    path('<int:pk>/summary/', views.QuestSubmissionSummary.as_view(), name='summary'),
    path('<int:pk>/summary/ajax', views.ajax_summary_histogram, name='ajax_summary_histogram'),

    # Submissions
    re_path(r'^submission/(?P<submission_id>[0-9]+)/skip/$', views.skip, name='skip'),
    re_path(r'^submission/(?P<submission_id>[0-9]+)/$', views.submission, name='submission'),
    re_path(r'^submission/(?P<submission_id>[0-9]+)/drop/$', views.drop, name='drop'),
    re_path(r'^submission/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),
    re_path(r'^submission/save/$', views.ajax_save_draft, name='ajax_save_draft'),
    re_path(r'^submission/(?P<submission_id>[0-9]+)/approve/$', views.ApproveView.as_view(), name='approve'),
    re_path(r'^submission/past/(?P<submission_id>[0-9]+)/$', views.submission, name='submission_past'),

    # Flagged submissions
    re_path(r'^submission/(?P<submission_id>[0-9]+)/flag/$', views.flag, name='flag'),
    re_path(r'^submission/(?P<submission_id>[0-9]+)/unflag/$', views.unflag, name='unflag'),

    # Campaigns / Categories
    path('campaigns/', views.CategoryList.as_view(), name='categories'),
    path('campaigns/available/', views.CategoryList.as_view(), name='categories_available'),
    path('campaigns/inactive/', views.CategoryList.as_view(), name='categories_inactive'),
    path('campaigns/add/', views.CategoryCreate.as_view(), name='category_create'),
    path('campaigns/<pk>/', views.CategoryDetail.as_view(), name='category_detail'),
    path('campaigns/<pk>/edit/', views.CategoryUpdate.as_view(), name='category_update'),
    path('campaigns/<pk>/delete/', views.CategoryDelete.as_view(), name='category_delete'),
    path('campaigns/<pk>/share/', views.CategoryShare.as_view(), name='category_share'),

    path('common-quest-info/list/', views.CommonDataListView.as_view(), name='commonquestinfo_list'),
    path('common-quest-info/create/', views.CommonDataCreateView.as_view(), name='commonquestinfo_create'),
    path('common-quest-info/update/<pk>/', views.CommonDataUpdateView.as_view(), name='commonquestinfo_update'),
    path('common-quest-info/delete/<pk>/', views.CommonDataDeleteView.as_view(), name='commonquestinfo_delete'),
]
