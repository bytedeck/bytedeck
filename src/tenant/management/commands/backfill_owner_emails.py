from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from allauth.account.models import EmailAddress
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
    without waiting for the nightly task.

    Every run also audits the owners that need a human: owners with no email at
    all, and owners still on the initial heuristic default account (the deck
    never chose a real owner). Where the deprecated public-tenant
    ``Tenant.owner_email`` disagrees with the owner's address, the line says so:
    it is often the best clue to who the owner should be.
    """

    help = (
        "Normalize every deck owner's allauth EmailAddress to verified+primary, matching "
        "what deck creation sets up. Dry-run by default; pass --apply to write. Also "
        "audits owners with no email and decks still on the heuristic default owner."
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

    def handle(self, *args, **options):
        """Iterate every billable tenant, print one audit line each, then a summary."""
        apply_changes = options['apply']
        tenants = get_tenant_model().objects.exclude(
            schema_name__in=[get_public_schema_name(), get_library_schema_name()]
        ).order_by('schema_name')

        header = f"{'deck':<24} {'status':<10} {'owner':<20} {'email':<32} notes"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        counts = {'ok': 0, 'fixed': 0, 'no-email': 0, 'error': 0}
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
        if default_owner_decks:
            summary += f"; {default_owner_decks} still on the default owner account"
        if counts['error']:
            summary += f"; {counts['error']} with errors"
        self.stdout.write(f"{summary}.")
        if not apply_changes:
            self.stdout.write("Dry run: no changes were written. Re-run with --apply to write.")

    def _process_deck(self, tenant, apply_changes):
        """Audit (and in apply mode normalize) one deck's owner email bookkeeping.

        Must run inside the deck's tenant context.

        Args:
            tenant (Tenant): The deck being processed (its public-schema row).
            apply_changes (bool): When True, write the EmailAddress fixes and
                refresh the deck's cached fields; when False, only report.

        Returns:
            tuple: ``(status, owner_name, email, notes)`` where ``status`` is
            ``ok`` (nothing to do), ``fixed`` (bookkeeping created or corrected;
            in dry-run mode this means it WOULD be), or ``no-email`` (needs a
            human); ``owner_name`` is the owner's username; ``email`` is the
            owner's address or None; ``notes`` is the semicolon-joined audit
            remarks for the report line.
        """
        from siteconfig.models import SiteConfig

        owner = SiteConfig.get().deck_owner
        notes = []
        # the initial deck_owner default was a heuristic (oldest non-admin staff
        # user, else a bare created account): flag decks that never chose for real
        if owner.username == settings.TENANT_DEFAULT_OWNER_USERNAME:
            notes.append("default owner account (heuristic guess, never chosen)")
        # the deprecated hand-entered public-tenant address is often the best clue
        # to who the owner SHOULD be when the schema's data is missing or wrong
        legacy = (tenant.owner_email or '').strip()
        if legacy and legacy.lower() != (owner.email or '').lower():
            notes.append(f"public-tenant legacy owner_email differs: {legacy}")

        if not owner.email:
            return 'no-email', owner.username, None, '; '.join(notes)

        # deterministic target row: prefer the exact-case match, else the oldest
        # case-variant duplicate (legacy data can hold several case variants)
        matches = list(EmailAddress.objects.filter(user=owner, email__iexact=owner.email).order_by('pk'))
        email_address = next((row for row in matches if row.email == owner.email), matches[0] if matches else None)
        already_ok = (
            email_address is not None and email_address.verified and email_address.primary
            and not EmailAddress.objects.filter(user=owner, primary=True).exclude(pk=email_address.pk).exists()
        )
        if already_ok:
            return 'ok', owner.username, owner.email, '; '.join(notes)

        if apply_changes:
            # mirror TenantCreate.form_valid: the owner's address exists, verified
            # and primary. Every OTHER primary row is demoted BEFORE the target
            # saves: the DB allows at most one primary per user
            # (unique_primary_email), so the demote must come first, and excluding
            # by pk (a brand-new target has none, so nothing is spared) also
            # demotes a case-variant duplicate of the owner's own address.
            if email_address is None:
                email_address = EmailAddress(user=owner, email=owner.email, verified=True, primary=True)
            else:
                email_address.verified = True
                email_address.primary = True
            EmailAddress.objects.filter(user=owner, primary=True).exclude(pk=email_address.pk).update(primary=False)
            email_address.full_clean()
            email_address.save()
            # land owner_email_cached now; the notice engine and the Stripe
            # backfill report read the cache, not the schema
            tenant.update_cached_fields()
        return 'fixed', owner.username, owner.email, '; '.join(notes)
