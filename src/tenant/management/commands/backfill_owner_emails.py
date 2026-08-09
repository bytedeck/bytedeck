from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context

from library.utils import get_library_schema_name


class Command(BaseCommand):
    """Backfill allauth EmailAddress bookkeeping for legacy deck owners (#1729 rollout).

    Deck creation marks the owner's EmailAddress verified and primary
    (TenantCreate.form_valid), but owners of decks created before that flow often
    have a ``User.email`` with no allauth ``EmailAddress`` row at all. This
    command brings every deck owner up to the same state deck creation produces
    today: the ``EmailAddress`` row matching ``owner.email`` exists, is verified,
    and is the owner's only primary address. Marking legacy addresses verified is
    a deliberate maintainer decision (2026-08-01): they are long-standing
    customer contact addresses, and verification gates nothing
    security-sensitive here (sign-in and password reset already work
    unverified).

    Dry-run by default: pass ``--apply`` to write. In apply mode each fixed
    deck's cached fields are refreshed immediately so ``owner_email_cached`` (the
    address the notice engine and the Stripe backfill report use) is correct
    without waiting for the nightly task. ``--schema <deck>`` narrows the run to
    a single deck, for cleaning up one legacy deck by hand.

    Every run also audits the owners that need a human: owners with no email at
    all, owners whose address is already verified by a different account on the
    deck (the DB allows one verified row per address, so which account is really
    the owner's is a human call), and owners still on the initial heuristic
    default account (the deck never chose a real owner). Where the deprecated
    public-tenant ``Tenant.owner_email`` disagrees with the owner's address, the
    line says so: it is often the best clue to who the owner should be.
    """

    help = (
        "Normalize every deck owner's allauth EmailAddress to verified+primary, matching "
        "what deck creation sets up. Dry-run by default; pass --apply to write and "
        "--schema <deck> to process a single deck. Also audits owners with no email, "
        "addresses already verified by another account, and decks still on the "
        "heuristic default owner."
    )

    def add_arguments(self, parser):
        """Register the --apply flag (without it the command only reports).

        Args:
            parser (argparse.ArgumentParser): The command's argument parser,
                mutated in place. Returns nothing.
        """
        parser.add_argument(
            '--apply', action='store_true',
            help="Write the EmailAddress fixes and refresh each fixed deck's cached fields. "
                 "Without this flag nothing is written.",
        )
        parser.add_argument(
            '--schema', default=None,
            help="Only process this one deck (its schema name), e.g. a single legacy deck "
                 "being cleaned up by hand. Without it every deck is processed.",
        )

    def handle(self, *args, **options):
        """Iterate the selected billable tenant(s), print one audit line each, then a summary."""
        apply_changes = options['apply']
        tenants = get_tenant_model().objects.exclude(
            schema_name__in=[get_public_schema_name(), get_library_schema_name()]
        ).order_by('schema_name')
        if options['schema']:
            tenants = tenants.filter(schema_name=options['schema'])
            if not tenants.exists():
                raise CommandError(
                    f"No deck with schema name '{options['schema']}' "
                    "(the public and library schemas are not decks)."
                )

        header = f"{'deck':<24} {'status':<10} {'owner':<20} {'email':<32} notes"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        counts = {'ok': 0, 'fixed': 0, 'no-email': 0, 'skipped': 0, 'error': 0}
        default_owner_decks = 0
        for tenant in tenants:
            try:
                # atomic() makes each deck a savepoint, so one broken schema can't
                # poison the connection (aborted transaction) for the remaining decks
                with transaction.atomic(), tenant_context(tenant):
                    status, owner_name, email, notes = self._process_deck(tenant, apply_changes)
            except Exception as e:
                counts['error'] += 1
                self.stdout.write(f"{tenant.schema_name:<24} {'ERROR':<10} {'-':<20} {'-':<32} {type(e).__name__}: {e}")
                continue
            counts[status] += 1
            if 'default owner account' in notes:
                default_owner_decks += 1
            label = status if (apply_changes or status != 'fixed') else 'would-fix'
            self.stdout.write(f"{tenant.schema_name:<24} {label:<10} {owner_name:<20} {email or '-':<32} {notes}")

        self.stdout.write("-" * len(header))
        summary = (
            f"{tenants.count()} deck(s): {counts['ok']} already ok, "
            f"{counts['fixed']} {'fixed' if apply_changes else 'would be fixed'}, "
            f"{counts['no-email']} with no owner email (fix by hand in the SiteConfig admin)"
        )
        if counts['skipped']:
            summary += f"; {counts['skipped']} skipped (address verified by another account: fix by hand)"
        if default_owner_decks:
            summary += f"; {default_owner_decks} still on the default owner account"
        if counts['error']:
            summary += f"; {counts['error']} with errors"
        self.stdout.write(f"{summary}.")
        if not apply_changes:
            self.stdout.write("Dry run: no changes were written. Re-run with --apply to write.")

    def _process_deck(self, tenant, apply_changes):
        """Audit (and in apply mode normalize) one deck's owner email bookkeeping.

        Thin wrapper over :func:`tenant.utils.normalize_owner_email` (the single
        write path this command shares with the tenant admin's "Verify owner
        email" action). Must run inside the deck's tenant context.

        Args:
            tenant (Tenant): The deck being processed (its public-schema row).
            apply_changes (bool): When True, write the EmailAddress fixes and
                refresh the deck's cached fields; when False, only report.

        Returns:
            tuple: The helper's ``(status, owner_name, email, notes)``.
        """
        from tenant.utils import normalize_owner_email

        return normalize_owner_email(tenant, apply_changes)
