from django.urls import path

from competencies import views

app_name = 'competencies'

urlpatterns = [
    path('', views.CompetencyListView.as_view(), name='list'),
    path('import/', views.CompetencyImportView.as_view(), name='import'),
    path('import/preview/', views.CompetencyImportPreviewView.as_view(), name='import_preview'),
    path('export/', views.CompetencyExportView.as_view(), name='export'),
    path('summary/<int:user_pk>/', views.CompetencySummaryView.as_view(), name='summary'),
    path('matrix/', views.CompetencyMatrixView.as_view(), name='matrix'),
    path('override/<int:user_pk>/<int:competency_pk>/', views.CompetencyOverrideView.as_view(), name='override'),
]
