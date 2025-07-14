from django.urls import path
from library import views

app_name = 'library'

urlpatterns = [
    path('quests-list/', views.LibraryQuestListView.as_view(), name='quest_list'),
    path('campaign-list/', views.LibraryCampaignListView.as_view(), name='category_list'),
    path('import-campaign/<uuid:campaign_import_id>/', views.ImportCampaignView.as_view(), name='import_category'),
    path('import-quest/<uuid:quest_import_id>/', views.ImportQuestView.as_view(), name='import_quest'),
]
