"""Helpers for the Font Awesome icon stored on :class:`courses.models.Rank`.

Ranks store the icon as a bare Font Awesome 4.7.0 name (``star``) in ``fa_icon``
plus any extra classes (``fa-rotate-270``, stack/sizing classes) in
``fa_icon_modifiers``; templates compose ``fa fa-<name> <modifiers>`` via
``Rank.fa_icon_class``. Before that split the single ``fa_icon`` field held a
whole class list (``fa fa-forward fa-rotate-270``). ``split_fa_icon_value`` is
the one-time conversion, kept here (not inline in the migration) so it can be
unit-tested directly.
"""
import re

# Matches every "fa-<something>" class token, so it also plucks the icon out of a
# value that was (against the old, misleading help text) typed as real HTML.
_FA_TOKEN_RE = re.compile(r"fa-[\w-]+")


def split_fa_icon_value(raw):
    """Split a legacy ``Rank.fa_icon`` value into ``(bare_name, modifiers)``.

    Handles every historical shape:

    * full class list ``"fa fa-forward fa-rotate-270"`` -> ``("forward", "fa-rotate-270")``
    * plain icon ``"fa fa-star"`` -> ``("star", "")``
    * prefix-only ``"fa-diamond"`` -> ``("diamond", "")``
    * already bare ``"star-o"`` -> ``("star-o", "")``
    * icon buried in HTML ``'<i class="fa fa-star"></i>'`` -> ``("star", "")``
    * empty / unparseable -> ``("", "")``

    The first ``fa-<x>`` token is taken as the icon; any remaining ``fa-<x>``
    tokens are kept as modifiers. A value with no ``fa-`` token is treated as an
    already-bare name (ignoring a stray base ``fa``).

    :param raw: the stored value (may be ``None``).
    :return: a ``(bare_name, modifiers)`` tuple of stripped strings.
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""

    fa_tokens = _FA_TOKEN_RE.findall(raw)
    if not fa_tokens:
        # No "fa-" token at all: a lone bare name like "star-o" (ignore a stray "fa").
        words = [word for word in raw.split() if word and word != "fa"]
        return (words[0], "") if len(words) == 1 else ("", "")

    name = fa_tokens[0][len("fa-"):]
    modifiers = " ".join(fa_tokens[1:])
    return name, modifiers
