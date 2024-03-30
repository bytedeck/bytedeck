from django.urls import path
from library import views

app_name = 'library'

urlpatterns = [
    path(r'', views.list_library_quests, name='library_quest_list'),
    path('import/bulk/', views.import_quest_to_current_deck_bulk, name='import_quest_bulk'),
    path('import/<uuid:quest_import_id>/', views.import_quest_to_current_deck, name='import_quest'),
]
