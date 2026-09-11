"""Tests for the From header the app builds for the email a deck sends."""
from email.utils import parseaddr

from django.core.mail.message import sanitize_address
from django.test import SimpleTestCase, override_settings

from utilities.mail import deck_from_email


class DeckFromEmailTest(SimpleTestCase):
    """``deck_from_email`` names the deck as the sender while keeping the configured
    sending address. Pure function reading settings, so no database is needed."""

    @override_settings(DEFAULT_FROM_EMAIL="contact@bytedeck.com")
    def test_deck_from_email__names_the_deck_before_a_bare_address(self):
        """A bare DEFAULT_FROM_EMAIL keeps its address and gains the deck's domain as the
        display name."""
        self.assertEqual(deck_from_email("deckname.bytedeck.com"),
                         '"deckname.bytedeck.com" <contact@bytedeck.com>')

    @override_settings(DEFAULT_FROM_EMAIL="Byte Deck <contact@bytedeck.com>")
    def test_deck_from_email__replaces_a_display_name_the_setting_already_has(self):
        """DEFAULT_FROM_EMAIL can legitimately carry a display name of its own, which is the
        shape Django's docs show and what production uses. Only its address is kept, so the
        deck's name is not nested inside it."""
        self.assertEqual(deck_from_email("deckname.bytedeck.com"),
                         '"deckname.bytedeck.com" <contact@bytedeck.com>')

    @override_settings(DEFAULT_FROM_EMAIL="Byte Deck <contact@bytedeck.com>")
    def test_deck_from_email__is_an_address_django_will_send(self):
        """The composed header survives the check the SMTP backend runs on the way out.

        This is the check that decides whether the mail is sent at all: sanitize_address
        raises ValueError on a header carrying two display names, such as
        '"deck" <Byte Deck <contact@bytedeck.com>>', which would take down every
        notification digest and announcement email inside its Celery task.
        """
        sanitized = sanitize_address(deck_from_email("adventure.bytedeck.com"), "utf-8")
        self.assertEqual(parseaddr(sanitized)[1], "contact@bytedeck.com")

    @override_settings(DEFAULT_FROM_EMAIL="")
    def test_deck_from_email__unset_leaves_the_sender_to_django(self):
        """With nothing configured there is no address to name a deck against, so the From
        is left for Django to fill in from its own default."""
        self.assertIsNone(deck_from_email("deckname.bytedeck.com"))

    @override_settings(DEFAULT_FROM_EMAIL=None)
    def test_deck_from_email__none_leaves_the_sender_to_django(self):
        """The setting defaults to None when the deployment does not set it at all."""
        self.assertIsNone(deck_from_email("deckname.bytedeck.com"))

    @override_settings(DEFAULT_FROM_EMAIL="Byte Deck")
    def test_deck_from_email__a_value_holding_no_address_leaves_the_sender_to_django(self):
        """A misconfigured value with no address in it cannot be sent from, so it is passed
        over rather than composed into a header that would fail at send time."""
        self.assertIsNone(deck_from_email("deckname.bytedeck.com"))
