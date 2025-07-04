from django.urls import path
from library.views import (
    LibraryQuestListView,
    LibraryCampaignListView,
    ImportCampaignView,
    ImportQuestView,
)

app_name = 'library'

urlpatterns = [
    path('quests/', LibraryQuestListView.as_view(), name='quest_list'),
    path('campaigns/', LibraryCampaignListView.as_view(), name='category_list'),
    path('import-campaign/<uuid:campaign_import_id>/', ImportCampaignView.as_view(), name='import_category'),
    path('import/<uuid:quest_import_id>/', ImportQuestView.as_view(), name='import_quest'),
]
