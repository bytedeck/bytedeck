from django.urls import path

from competencies import views

app_name = 'competencies'

urlpatterns = [
    path('', views.CompetencyListView.as_view(), name='list'),
    path('import/', views.CompetencyImportView.as_view(), name='import'),
    path('import/preview/', views.CompetencyImportPreviewView.as_view(), name='import_preview'),
    path('export/', views.CompetencyExportView.as_view(), name='export'),
    path('evidence/<int:user_pk>/<int:competency_pk>/', views.CompetencyEvidenceView.as_view(), name='evidence'),
]
