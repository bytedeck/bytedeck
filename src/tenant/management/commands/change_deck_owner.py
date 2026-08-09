from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context

from library.utils import get_library_schema_name


class Command(BaseCommand):
    """Change a deck's owner to another staff user on that deck (legacy cleanup).

    Mirrors what choosing a new Deck Owner in the SiteConfig admin does
    (``SiteConfigForm.clean_deck_owner``): the new owner must be an existing
    STAFF user on the deck and is promoted to superuser. The previous owner's
    account and permissions are left untouched (demote them by hand if wanted).
    The deck's cached owner fields are refreshed immediately so the public
    admin, the notice engine, and the Stripe backfill report see the new owner
    without waiting for the nightly task.

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
        """Validate the deck and user, then switch the owner and refresh caches."""
        from siteconfig.models import SiteConfig

        User = get_user_model()
        Tenant = get_tenant_model()
        schema_name = options['schema_name']
        if schema_name in (get_public_schema_name(), get_library_schema_name()):
            raise CommandError(f"'{schema_name}' is not a deck.")
        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            raise CommandError(f"No deck with schema name '{schema_name}'.")

        with transaction.atomic(), tenant_context(tenant):
            try:
                new_owner = User.objects.get(username=options['username'])
            except User.DoesNotExist:
                raise CommandError(f"No user '{options['username']}' on deck '{schema_name}'.")
            if not new_owner.is_staff:
                raise CommandError(
                    f"'{new_owner.username}' is not a staff user on '{schema_name}': the deck owner "
                    "must be staff. Make them staff first if this really is the right account."
                )
            config = SiteConfig.get()
            old_owner = config.deck_owner
            if old_owner == new_owner:
                self.stdout.write(f"'{new_owner.username}' already owns '{schema_name}'; nothing to do.")
                return
            # mirror SiteConfigForm.clean_deck_owner: the deck owner is always a superuser
            if not new_owner.is_superuser:
                new_owner.is_superuser = True
                new_owner.save()
            config.deck_owner = new_owner
            config.full_clean()
            config.save()
            # land the cached owner name/email now; the public admin, the notice
            # engine, and the Stripe backfill report all read the cache
            tenant.update_cached_fields()

        self.stdout.write(self.style.SUCCESS(
            f"'{schema_name}' owner changed: {old_owner.username} -> {new_owner.username} "
            "(promoted to superuser; the previous owner's permissions are untouched)."
        ))
        self.stdout.write(
            f"Reminder: run `backfill_owner_emails --schema {schema_name} --apply` to "
            "normalize the new owner's email verification."
        )
