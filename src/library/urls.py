from django.urls import path
from library import views

app_name = 'library'

urlpatterns = [
    path('quests/', views.LibraryQuestListView.as_view(), name='quest_list'),
    path('campaigns/', views.LibraryCampaignListView.as_view(), name='category_list'),
    path('import-campaign/<uuid:campaign_import_id>/', views.ImportCampaignView.as_view(), name='import_category'),
    path('import/<uuid:quest_import_id>/', views.ImportQuestView.as_view(), name='import_quest'),
]
