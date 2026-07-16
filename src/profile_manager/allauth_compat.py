"""Drop-in replacements for helpers removed from django-allauth in 65.x.

``allauth.utils.email_address_exists`` and
``allauth.account.utils.send_email_confirmation`` were public in allauth 0.54
but no longer exist in 65.x. These reimplementations preserve the old
signatures and semantics so the call sites in this app stay unchanged.
"""
from allauth.account.internal.flows.email_verification import (
    send_verification_email_to_address,
)
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from django.contrib.auth import get_user_model


def email_address_exists(email, exclude_user=None):
    """Return True if any other user already has this email address.

    The address counts as taken if it appears (case-insensitively) either in
    allauth's ``EmailAddress`` table or in ``User.email``, ignoring
    ``exclude_user`` (the user whose profile is being edited).
    """
    emailaddresses = EmailAddress.objects
    if exclude_user:
        emailaddresses = emailaddresses.exclude(user=exclude_user)
    if emailaddresses.filter(email__iexact=email).exists():
        return True

    users = get_user_model().objects
    if exclude_user:
        users = users.exclude(pk=exclude_user.pk)
    return users.filter(email__iexact=email).exists()


def send_email_confirmation(request, user, signup=False, email=None):
    """Ensure ``email`` has an ``EmailAddress`` record and (re)send its
    verification email if it is not verified yet.

    Like the old allauth helper, this rate-limits resends, shows the
    "confirmation e-mail sent" message, and fires the
    ``email_confirmation_sent`` signal (which ``profile_manager.models``
    listens to) — all handled inside allauth's email-verification flow.
    """
    email = email or user_email(user)
    if not email:
        return

    email_address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if email_address is None:
        # creates the (unverified) EmailAddress without sending, so the
        # send below is the single code path for the verification email
        email_address = EmailAddress.objects.add_email(request, user, email, confirm=False)

    if not email_address.verified:
        send_verification_email_to_address(request, email_address, signup=signup)
