from django.core.management.base import BaseCommand

from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context


class Command(BaseCommand):
    """Read-only report of every deck's billing status and active-user counts.

    For each non-public tenant, prints the derived billing status (subscribed /
    grace / trial / suspended / unmanaged), the trial and paid dates, the stored
    (cached) active_user_count, a freshly recomputed count, and the delta between
    them. Nothing is written, so the whole command is a dry run by design: use it
    to review the effect of counting changes (e.g. the staff double-count fix,
    epic #1729 PR 1) against live data before any enforcement or notification
    behavior ships (#1729 rollout plan).
    """

    help = (
        "Print a read-only per-deck report of billing status and stored-vs-recomputed "
        "active-user counts. Writes nothing."
    )

    def handle(self, *args, **options):
        """Iterate every non-public tenant and print one status/count line each, then a summary."""
        tenants = get_tenant_model().objects.exclude(schema_name=get_public_schema_name()).order_by('schema_name')

        header = f"{'deck':<24} {'status':<10} {'trial_end':<12} {'paid_until':<12} {'cached':>6} {'fresh':>6} {'delta':>6}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        changed = 0
        for tenant in tenants:
            with tenant_context(tenant):
                fresh_count = tenant.get_active_user_count()
            delta = fresh_count - tenant.active_user_count
            if delta:
                changed += 1
            self.stdout.write(
                f"{tenant.schema_name:<24} {self.billing_status(tenant):<10} "
                f"{str(tenant.trial_end_date or '-'):<12} {str(tenant.paid_until or '-'):<12} "
                f"{tenant.active_user_count:>6} {fresh_count:>6} {delta:>+6}"
            )

        self.stdout.write("-" * len(header))
        self.stdout.write(f"{tenants.count()} deck(s); {changed} with a count delta. No changes were written.")

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
