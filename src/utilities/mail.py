"""Helpers for the email the app sends."""

from email.utils import formataddr, parseaddr

from django.conf import settings


def deck_from_email(deck_domain):
    """The From header for an email one deck sends, naming that deck as the sender.

    A recipient who is on several decks can tell them apart at a glance (#2338), while the
    address itself stays the one the mail server is authorised to send from.

    Only the address part of ``DEFAULT_FROM_EMAIL`` is used, because it can legitimately be
    configured either as a bare address (``contact@example.com``) or with a display name of
    its own (``Byte Deck <contact@example.com>``), which is the shape Django's own
    documentation shows. ``formataddr`` puts whatever it is given straight into the address
    slot, so it has to be handed an address and nothing else: a header carrying two display
    names, ``"deck.example.com" <Byte Deck <contact@example.com>>``, is not a valid address,
    and Django's ``sanitize_address`` raises ``ValueError`` rather than sending it.

    Args:
        deck_domain (str): the deck's domain, e.g. "deckname.bytedeck.com".

    Returns:
        str or None: the composed From header, or None when ``DEFAULT_FROM_EMAIL`` is unset
        or holds nothing that reads as an address, which leaves the sender to Django's own
        default. ``parseaddr`` returns the first word of a value like "Byte Deck" as its
        address, so an address is only taken as one when it carries an "@".
    """
    _, sender_address = parseaddr(settings.DEFAULT_FROM_EMAIL or '')
    if '@' not in sender_address:
        return None
    return formataddr((deck_domain, sender_address))
