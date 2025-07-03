from django.urls import path
from library import views

app_name = 'library'

urlpatterns = [
    # AJAX endpoints
    path('quests/ajax_list/', views.ajax_quest_library_list, name='ajax_quest_library_list'),
    path('quests/ajax_quest_info/<int:id>/', views.ajax_quest_info, name='ajax_library_info'),
    path('quests/ajax_quest_info/', views.ajax_quest_info, name='ajax_library_root'),

    # Library pages
    path('quests/', views.quests_library_list, name='quest_list'),
    path('campaigns/', views.campaigns_library_list, name='category_list'),

    # Import
    path('import-campaign/<uuid:campaign_import_id>/', views.import_campaign, name='import_category'),
    path('import/<uuid:quest_import_id>/', views.import_quest_to_current_deck, name='import_quest'),
]
