import re

from django.db import migrations
from django.db.models import Q


# Font Awesome 4.7.0 classes that modify an icon rather than name one. Matched
# whole, so a real icon name that merely begins like one ("fa-list" beside the
# "fa-li" list marker, "fa-spinner" beside "fa-spin", "fa-stack-overflow" beside
# "fa-stack") is read as an icon.
_FA_MODIFIERS = frozenset((
    "fa-lg", "fa-2x", "fa-3x", "fa-4x", "fa-5x", "fa-fw", "fa-ul", "fa-li",
    "fa-border", "fa-spin", "fa-pulse", "fa-inverse",
    "fa-stack", "fa-stack-1x", "fa-stack-2x",
))

# The modifier families whose class name carries a value: fa-pull-left,
# fa-rotate-90, fa-flip-horizontal, and so on. No 4.7.0 icon name starts with one.
_FA_MODIFIER_FAMILIES = ("fa-pull-", "fa-rotate-", "fa-flip-")

# The shape Rank.fa_icon accepts, the pattern its validator carries, requiring a
# name. A recovered name is checked against it, so this migration cannot write a
# value the field would refuse.
_ICON_NAME_RE = re.compile(r"(?!fa-)[a-z0-9-]+")


def _is_modifier(token):
    """True if a "fa-<x>" token is a modifier/sizing class, not an icon name."""
    return token in _FA_MODIFIERS or token.startswith(_FA_MODIFIER_FAMILIES)


def recover_icon_name(modifiers):
    """Pull a stranded icon name out of a ``fa_icon_modifiers`` value.

    Returns ``(icon_name, remaining_modifiers)``: the first "fa-" token that names
    an icon rather than modifying one, with its prefix stripped, and the rest of
    the value with that token removed. ``("", modifiers)`` when every token really
    is a modifier, which is the untouched case.

    Kept inside the migration (not imported from application code) so this one-time
    data repair stays frozen, the same reason ``0030`` carries its own splitter.

    ``"fa-list"`` -> ``("list", "")``, ``"fa-fw fa-list"`` -> ``("list", "fa-fw")``,
    ``"fa-list fa-rotate-90"`` -> ``("list", "fa-rotate-90")``, and a genuine
    ``"fa-rotate-270"`` -> ``("", "fa-rotate-270")``. Only "fa-" tokens are
    candidates, since those are the only shape ``0030`` wrote here.
    """
    tokens = (modifiers or "").split()
    for index, token in enumerate(tokens):
        if not token.startswith("fa-") or _is_modifier(token):
            continue
        name = token[len("fa-"):]
        if not _ICON_NAME_RE.fullmatch(name):
            continue
        return name, " ".join(tokens[:index] + tokens[index + 1:])
    return "", modifiers


def repair_rank_fa_icon_names(apps, schema_editor):
    """Give back the icon to ranks that ``0030`` left with an empty ``fa_icon``.

    ``0030`` decided which class tokens were modifiers with a ``startswith`` test,
    and three of the prefixes it tested ("fa-li", "fa-spin", "fa-stack") also begin
    15 real Font Awesome 4.7.0 icon names, among them fa-list, fa-link, fa-linux,
    fa-life-ring, fa-lightbulb-o, fa-spinner and fa-stack-overflow. A rank holding
    one of those came out with ``fa_icon=""`` and the name sitting in
    ``fa_icon_modifiers``, and ``Rank.fa_icon_class`` renders nothing without a
    name, so those ranks show no icon at all.

    The name was never lost, only misfiled, so this moves it back. ``0030`` itself
    is left alone: it is already applied on live decks, so editing it would repair
    nothing there.
    """
    Rank = apps.get_model("courses", "Rank")
    stranded = Rank.objects.filter(Q(fa_icon__isnull=True) | Q(fa_icon="")).exclude(fa_icon_modifiers="")
    for rank in stranded:
        name, modifiers = recover_icon_name(rank.fa_icon_modifiers)
        if not name:
            continue
        rank.fa_icon = name
        rank.fa_icon_modifiers = modifiers
        rank.save(update_fields=["fa_icon", "fa_icon_modifiers"])


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0032_alter_rank_fa_icon"),
    ]

    operations = [
        # No reverse: this puts a rank's icon where the field has always meant to
        # hold it, so there is nothing to undo, and unapplying leaves every icon
        # rendering. Should 0030 be unapplied afterwards, its own reverse folds the
        # name and modifiers back into one class list, which for a repaired rank
        # rebuilds exactly the "fa fa-list" it started from.
        migrations.RunPython(repair_rank_fa_icon_names, migrations.RunPython.noop),
    ]
