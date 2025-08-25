from django.urls import path

from . import views

app_name = 'tenant'

urlpatterns = [
    path('new/', views.TenantCreate.as_view(), name='new'),
    path("request-new-deck/", views.RequestNewDeck.as_view(), name="request_new_deck"),
    path("request-new-deck/verify/<path:token>/", views.verify_deck_request, name="verify_deck_request"),
]
