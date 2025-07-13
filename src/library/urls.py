from django.urls import path
from library import views

app_name = 'library'

urlpatterns = [
    path('quests-list/', views.quests_library_list, name='quest_list'),
    path('campaign-list/', views.campaigns_library_list, name='category_list'),
    path('import-campaign/<uuid:campaign_import_id>/', views.import_campaign, name='import_category'),
    path('import/<uuid:quest_import_id>/', views.import_quest_to_current_deck, name='import_quest'),
]
