from django.core.management.base import BaseCommand, CommandError

from django_tenants.utils import get_public_schema_name, get_tenant_model

from library.utils import get_library_schema_name


class Command(BaseCommand):
    """Change a deck's owner to another staff user on that deck (legacy cleanup).

    Thin CLI wrapper over :func:`tenant.utils.switch_deck_owner`, the single
    write path this command shares with the tenant admin's "Change deck owner"
    action: the new owner must be an existing STAFF user on the deck and is
    promoted to superuser (mirroring ``SiteConfigForm.clean_deck_owner``); the
    previous owner's account and permissions are left untouched, and the deck's
    cached owner fields are refreshed immediately so the public admin, the
    notice engine, and the Stripe backfill report see the new owner without
    waiting for the nightly task.

    The new owner's email-verification bookkeeping is deliberately NOT touched
    here: run ``backfill_owner_emails --schema <deck> --apply`` afterwards to
    normalize their allauth EmailAddress to verified+primary.
    """

    help = (
        "Change a deck's owner (SiteConfig.deck_owner) to another staff user on that deck: "
        "change_deck_owner <schema_name> <username>. The new owner is promoted to superuser "
        "(matching the SiteConfig admin); afterwards run "
        "backfill_owner_emails --schema <deck> --apply to normalize their email verification."
    )

    def add_arguments(self, parser):
        """Register the deck schema and new-owner username arguments.

        Args:
            parser (argparse.ArgumentParser): The command's argument parser,
                mutated in place. Returns nothing.
        """
        parser.add_argument('schema_name', help="The deck's schema name, e.g. 'hackerspace'.")
        parser.add_argument('username', help="The new owner: an existing STAFF user on that deck.")

    def handle(self, *args, **options):
        """Validate the deck, then switch the owner via the shared helper."""
        from tenant.utils import switch_deck_owner

        Tenant = get_tenant_model()
        schema_name = options['schema_name']
        if schema_name in (get_public_schema_name(), get_library_schema_name()):
            raise CommandError(f"'{schema_name}' is not a deck.")
        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            raise CommandError(f"No deck with schema name '{schema_name}'.")

        try:
            old_username, new_username = switch_deck_owner(tenant, options['username'])
        except ValueError as e:
            raise CommandError(str(e))

        if old_username == new_username:
            self.stdout.write(f"'{new_username}' already owns '{schema_name}'; nothing to do.")
            return
        self.stdout.write(self.style.SUCCESS(
            f"'{schema_name}' owner changed: {old_username} -> {new_username} "
            "(promoted to superuser; the previous owner's permissions are untouched)."
        ))
        self.stdout.write(
            f"Reminder: run `backfill_owner_emails --schema {schema_name} --apply` to "
            "normalize the new owner's email verification."
        )
