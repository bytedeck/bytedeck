from django.db import migrations

#: Paths a homepage TRY IT button has pointed at over the life of the deck-request flow,
#: none of which a visitor can use now. The first two 404: they were the URLs before the
#: request flow landed. The third still resolves, which is what makes it the worst of them:
#: it is the form the flow reaches *after* the visitor has verified their email, so it is
#: behind EmailVerificationRequiredMixin and answers an ordinary visitor with a 403 "Deck
#: Request Required" page. Staff are let through, so to a signed-in maintainer the button
#: looks like it merely goes to an older form.
STALE_PATHS = (
    "/decks/new/",
    "/decks/request-new-deck/",
    "/decks/request/new/",
)

#: Where a visitor starts: the request form that emails them a verification link.
CURRENT_PATH = "/decks/request/"


def repoint_links(apps, schema_editor):
    """Point any hardcoded deck-request link in flatpage content at the current request form.

    The homepage is a FlatPage seeded by `initdb`, and `initdb` creates it with
    `get_or_create`, so a site set up before a URL moved keeps whatever content it had:
    the seeded HTML being right says nothing about what is stored. Only the exact href
    values above are rewritten, so a page someone has since edited keeps every other
    change they made.

    Args:
        apps: the historical app registry.
        schema_editor: unused; the migration is data-only.
    """
    FlatPage = apps.get_model("flatpages", "FlatPage")
    for flatpage in FlatPage.objects.all():
        content = flatpage.content
        for stale in STALE_PATHS:
            for quote in ('"', "'"):
                content = content.replace(f"href={quote}{stale}{quote}", f"href={quote}{CURRENT_PATH}{quote}")
        if content != flatpage.content:
            flatpage.content = content
            flatpage.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenant", "0030_decknotice_threshold_help"),
        ("flatpages", "0001_initial"),
    ]

    operations = [
        # No reverse: the stale paths are indistinguishable once rewritten, and putting a
        # visitor back on a link that 403s them is not a state worth restoring.
        migrations.RunPython(repoint_links, migrations.RunPython.noop),
    ]
