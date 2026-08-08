from django.core.management.base import BaseCommand
from django.db import transaction

from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context

from library.utils import get_library_schema_name


class Command(BaseCommand):
    """Read-only report of every deck's billing status and active-user counts.

    For each billable tenant (the public schema and the shared-library schema are
    excluded), prints the derived billing status (subscribed / grace / trial /
    suspended / unmanaged), the trial and paid dates, the stored (cached)
    active_user_count, a freshly recomputed count, and the delta between them.
    Nothing is written, so the whole command is a dry run by design: use it to
    review the effect of counting changes (e.g. the staff double-count fix, epic
    #1729 PR 1) against live data before any enforcement or notification behavior
    ships (#1729 rollout plan).

    Sequencing caveat: the tenant admin changelist refreshes every deck's cached
    counts with the current formula on each page load, so after deploying a
    counting change, run this BEFORE anyone opens that changelist -- otherwise the
    stored-vs-fresh deltas will already have been flattened to zero.

    A deck whose schema is broken or missing required rows (e.g. no SiteConfig) is
    reported as an ERROR line instead of aborting the whole report.
    """

    help = (
        "Print a read-only per-deck report of billing status and stored-vs-recomputed "
        "active-user counts. Writes nothing (dry-run by design). After deploying a "
        "counting change, run before the tenant admin changelist is next opened, or "
        "the deltas will already be flattened."
    )

    def handle(self, *args, **options):
        """Iterate every billable tenant and print one status/count line each, then a summary."""
        tenants = get_tenant_model().objects.exclude(
            schema_name__in=[get_public_schema_name(), get_library_schema_name()]
        ).order_by('schema_name')

        header = f"{'deck':<24} {'status':<10} {'trial_end':<12} {'paid_until':<12} {'cached':>6} {'fresh':>6} {'delta':>6}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        changed = 0
        errors = 0
        for tenant in tenants:
            try:
                # atomic() makes the recompute a savepoint, so one broken schema can't
                # poison the connection (aborted transaction) for the remaining decks
                with transaction.atomic(), tenant_context(tenant):
                    fresh_count = tenant.get_active_user_count()
            except Exception as e:
                errors += 1
                self.stdout.write(
                    f"{tenant.schema_name:<24} {'ERROR':<10} "
                    f"{str(tenant.trial_end_date or '-'):<12} {str(tenant.paid_until or '-'):<12} "
                    f"{tenant.active_user_count:>6} {'-':>6} {'-':>6}  ({type(e).__name__}: {e})"
                )
                continue
            delta = fresh_count - tenant.active_user_count
            if delta:
                changed += 1
            self.stdout.write(
                f"{tenant.schema_name:<24} {self.billing_status(tenant):<10} "
                f"{str(tenant.trial_end_date or '-'):<12} {str(tenant.paid_until or '-'):<12} "
                f"{tenant.active_user_count:>6} {fresh_count:>6} {delta:>+6}"
            )

        self.stdout.write("-" * len(header))
        summary = f"{tenants.count()} deck(s); {changed} with a count delta"
        if errors:
            summary += f"; {errors} with errors"
        self.stdout.write(f"{summary}. No changes were written.")

    @staticmethod
    def billing_status(tenant):
        """Return a one-word label for the tenant's derived billing status."""
        if tenant.subscription_active:
            return 'grace' if tenant.in_grace_period else 'subscribed'
        if tenant.is_on_trial:
            return 'trial'
        if tenant.is_suspended:
            return 'suspended'
        return 'unmanaged'
