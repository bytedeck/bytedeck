from django.conf.urls import  url
from badges import views

urlpatterns = [
    url(r'^$', views.list, name='list'),
    # url(r'^approvals/$', views.approvals, name='approvals'),
    # # url(r'^email_demo/$', views.email_demo, name='email_demo'),
    # # url(r'^new_quest_custom/$', views.new_quest_custom, name='new_quest_custom'),
    # # url(r'^quests/$', 'quest_manager.views.quests', name='quests'),
    #  # ex: /quest/25/
    # url(r'^create/$', views.quest_create, name='quest_create'),
    # url(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    # # url(r'^(?P<quest_id>[0-9]+)/edit/$', views.quest_update, name='quest_update'),
    # url(r'^(?P<pk>[0-9]+)/edit/$', views.QuestUpdate.as_view(), name='quest_update'),
    # url(r'^(?P<quest_id>[0-9]+)/copy/$', views.quest_copy, name='quest_copy'),
    # url(r'^(?P<pk>[0-9]+)/delete/$', views.QuestDelete.as_view(), name='quest_delete'),
    # url(r'^(?P<quest_id>[0-9]+)/start/$', views.start, name='start'),
    # url(r'^submission/(?P<submission_id>[0-9]+)/$', views.submission, name='submission'),
    # url(r'^submission/(?P<submission_id>[0-9]+)/drop/$', views.drop, name='drop'),
    # url(r'^submission/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),
    # url(r'^submission/(?P<submission_id>[0-9]+)/approve/$', views.approve, name='approve'),

]
