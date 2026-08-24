"""Shared pieces for the Font Awesome 4.7.0 icons stored across the app.

Four models let a user pick an icon (:class:`courses.models.Rank`,
:class:`badges.models.BadgeType`, :class:`badges.models.BadgeRarity` and
:class:`utilities.models.MenuItem`). They all store the same thing in the same
shape now: the **bare icon name** the picker widget writes (``star``, not
``fa-star`` and not ``fa fa-star``), which is also the unit
``static/js/fa_icons_4.7.0.js`` is keyed on. This module holds the validator,
help text and render helper they share, so the four fields cannot drift apart
again.
"""

from django.core.validators import RegexValidator
from django.utils.safestring import mark_safe


#: The stored value goes, unescaped, into an ``<i class="...">`` that several
#: templates render with ``|safe``, so a staff-entered value is held to safe
#: Font Awesome class tokens: one bare, lowercase name, no "fa-" prefix and no
#: spaces. Shared by every ``fa_icon`` field (one instance is fine: validators
#: hold no per-field state).
FA_ICON_VALIDATOR = RegexValidator(
    r'^(?!fa-)[a-z0-9-]*$',
    'Enter a single Font Awesome icon name in lowercase, e.g. "star" (no "fa-" prefix, no spaces).')

#: Says the same thing on every icon field: the picker is the easy way in, and
#: the link is pinned to 4.7.0 because that is the vendored version (a modern
#: Font Awesome list offers names like "circle-o" that 4.7.0 renamed, which
#: would render as a blank icon here).
FA_ICON_HELP_TEXT = mark_safe(
    'A Font Awesome icon name, e.g. "star". Use the picker to browse the options, or see the full list of '
    '<a target="_blank" rel="noopener" href="https://fontawesome.com/v4.7.0/icons/">Font Awesome 4.7.0 icons</a>.')


def bare_icon_name(value):
    """Return the bare Font Awesome icon name held in a stored ``fa_icon`` value.

    Bare names are what the fields hold, so this is usually just a trim. It also
    accepts the older ``fa-star`` and ``fa fa-star`` shapes, because a value can
    still arrive that way from outside a form: a badge CSV exported by a deck
    running an older version, or a row edited straight in the database.

    ``"star"``, ``"  star  "``, ``"fa-star"`` and ``"fa fa-star"`` all give
    ``"star"``; ``""`` and ``None`` give ``""``. A whole class list that puts a
    sizing class first (``"fa fa-fw fa-star"``) is beyond it: untangling those is
    the job of the one-time data migrations that normalized these fields, which
    carry their own frozen table of which classes are modifiers.
    """
    for token in (value or '').split():
        if token == 'fa':
            continue
        return token[len('fa-'):] if token.startswith('fa-') else token
    return ''


def fa_icon_class(value, modifiers=''):
    """Compose the class list to drop into ``<i class="...">``: ``fa fa-<name>``
    followed by any modifier classes (rotations, flips, ...).

    Returns '' when no icon is set, so a template renders a bare ``<i>`` rather
    than a stray "fa fa-".
    """
    name = bare_icon_name(value)
    if not name:
        return ''
    classes = 'fa fa-' + name
    modifiers = (modifiers or '').strip()
    return classes + ' ' + modifiers if modifiers else classes
