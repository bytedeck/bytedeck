from django.urls import path

from . import views

app_name = 'tenant'

urlpatterns = [
    path('new/', views.TenantCreate.as_view(), name='new'),
]
