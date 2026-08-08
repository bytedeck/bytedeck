from django.urls import path

from . import views

app_name = 'tenant'

urlpatterns = [
    # The whole deck-request flow lives under /decks/request/, in flow order:
    # request form -> "check your email" page -> emailed verify link -> new-deck info form
    path("request/", views.RequestNewDeck.as_view(), name="request_new_deck"),
    path("request/email-verification/", views.RequestNewDeckSubmitted.as_view(), name="request_new_deck_submitted"),
    path("request/verify/<path:nonce>/", views.verify_deck_request, name="verify_deck_request"),
    path("request/new/", views.TenantCreate.as_view(), name="new"),

    # Staff-facing subscription pages for the current deck (non-public tenants only,
    # epic #1729 PR 6): details/checkout, the post-checkout activating page, and its
    # JSON polling target.
    path("subscription/", views.SubscriptionDetail.as_view(), name="subscription"),
    path("subscription/activating/", views.SubscriptionActivating.as_view(), name="subscription_activating"),
    path("subscription/status/", views.subscription_status, name="subscription_status"),
]
