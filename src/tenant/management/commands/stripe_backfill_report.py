from django.conf import settings
from django.core.management.base import BaseCommand

from tenant.billing import to_plain_dict
from tenant.models import Tenant


class Command(BaseCommand):
    """Report how active Stripe subscriptions match up to decks (#2043, plan §10.3).

    READ-ONLY: lists every active subscription in the Stripe account and matches
    its customer email against each deck's cached owner email, emitting a
    human-review report -- it never links anything itself (auto-linking on an
    ambiguous match could bill the wrong school). To act on the report: paste the
    subscription id into the deck in the tenant admin, save, then run the
    "Sync selected deck(s) from Stripe" action.
    """
    help = ("Read-only report matching active Stripe subscriptions to decks by owner email "
            "(#2043 legacy backfill). Link matches by hand in the tenant admin, then use the "
            "'Sync from Stripe' admin action.")

    def handle(self, *args, **options):
        """Fetch active subscriptions and print matched / ambiguous / unmatched sections."""
        import stripe

        if not settings.STRIPE_SECRET_KEY:
            self.stdout.write(self.style.ERROR('Stripe is not configured (STRIPE_SECRET_KEY unset).'))
            return

        subscriptions = stripe.Subscription.list(
            api_key=settings.STRIPE_SECRET_KEY, status='active', expand=['data.customer'], limit=100,
        ).auto_paging_iter()

        matched, ambiguous, unmatched = [], [], []
        for subscription in subscriptions:
            # the SDK yields Subscription objects, which are not dicts on
            # stripe-python 15.x; the reads below all speak dict
            subscription = to_plain_dict(subscription)
            customer = subscription.get('customer') or {}
            email = (customer.get('email') or '').strip().lower()
            label = f"sub {subscription.get('id')} / customer {customer.get('id')} <{email or 'no email'}>"

            already = Tenant.objects.filter(stripe_subscription_id=subscription.get('id')).first()
            if already is not None:
                continue  # nothing to backfill
            decks = list(Tenant.objects.filter(owner_email_cached__iexact=email)) if email else []
            if len(decks) == 1:
                matched.append(f"{label}  ->  deck '{decks[0].schema_name}'")
            elif len(decks) > 1:
                names = ', '.join(d.schema_name for d in decks)
                ambiguous.append(f"{label}  ->  MULTIPLE decks: {names}")
            else:
                unmatched.append(f"{label}  ->  no deck with this owner email")

        for title, rows in (('MATCHED (link by hand, then run the admin sync action)', matched),
                            ('AMBIGUOUS (same owner email on multiple decks -- decide by hand)', ambiguous),
                            ('UNMATCHED (no deck found -- possibly a non-deck subscription)', unmatched)):
            self.stdout.write(f'\n== {title}: {len(rows)} ==')
            for row in rows:
                self.stdout.write('  ' + row)
        self.stdout.write(self.style.SUCCESS('\nReport only -- nothing was changed.'))
