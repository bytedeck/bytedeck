from datetime import date, timedelta

from django.core import mail
from django.core.cache import cache
from django.test import override_settings

from freezegun import freeze_time

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification
from tenant.models import DeckNotice, Tenant
from tenant.notices import evaluate_deck_notices, process_deck_notices
from tenant.utils import deck_cache_key

# Frozen mid-day UTC so timezone.localdate() (America/Vancouver) is the same calendar date.
TODAY = date(2026, 8, 15)
NOW = "2026-08-15 20:00:00"


@freeze_time(NOW)
@override_settings(DECK_NOTICES_ENABLED=True)
class DeckNoticeCadenceTest(ByteDeckTenantTestCase):
    """Tests for the reminder cadence engine (epic #1729 PR 5, #1733)."""

    def setUp(self):
        """Reset this deck to a known billing state and clear its cached row."""
        cache.delete(deck_cache_key(self.tenant.schema_name))
        # far-future trial, no subscription, empty deck: no notices due by default
        self.set_deck(trial_end_date=TODAY + timedelta(days=60), paid_until=None, active_user_count=0)

    def set_deck(self, **fields):
        """Persist billing fields via update() + refresh (ledger evaluation reads the instance)."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def due(self):
        """Shorthand: evaluate today's due notices for this deck."""
        return evaluate_deck_notices(self.tenant)

    def test_evaluate__nothing_due_far_from_any_deadline(self):
        """A quiet trial deck far from its deadline produces no notices."""
        self.assertEqual(self.due(), [])

    def test_evaluate__expiry_milestones_fire_once_each(self):
        """Entering the 30/14/7-day windows fires each milestone exactly once."""
        self.set_deck(trial_end_date=TODAY + timedelta(days=30))
        self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'd30', str(TODAY + timedelta(days=30)))])
        process_deck_notices(self.tenant)
        self.assertEqual(self.due(), [])  # d30 recorded; nothing more due today

    def test_evaluate__late_first_sight_fires_only_most_specific_milestone(self):
        """A deck first evaluated 10 days out gets ONE notice (d14), not a d30+d14 double."""
        self.set_deck(trial_end_date=TODAY + timedelta(days=10))
        self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'd14', str(TODAY + timedelta(days=10)))])

    def test_evaluate__daily_inside_final_week_and_through_grace(self):
        """After the milestones, one notice per day fires inside the final week, and keeps
        firing through the paid grace window (negative days)."""
        deadline = TODAY + timedelta(days=3)
        self.set_deck(trial_end_date=None, paid_until=deadline)
        process_deck_notices(self.tenant)  # consumes d7 (and only d7)
        self.assertEqual(DeckNotice.objects.filter(tenant=self.tenant).count(), 1)

        with freeze_time("2026-08-16 20:00:00"):
            self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'daily-2026-08-16', str(deadline))])
            process_deck_notices(self.tenant)
            self.assertEqual(self.due(), [])  # once per day only

        # 10 days after the deadline: in grace (30-day window), daily continues
        with freeze_time("2026-08-28 20:00:00"):
            self.assertIn((DeckNotice.KIND_EXPIRY, 'daily-2026-08-28', str(deadline)), self.due())

    def test_evaluate__beat_outage_catches_up_with_one_notice(self):
        """If beat is down for days, the next run sends one catch-up notice, not a backlog."""
        self.set_deck(trial_end_date=TODAY + timedelta(days=6))
        # no runs happen for 4 days...
        with freeze_time("2026-08-19 20:00:00"):
            due = self.due()
            self.assertEqual(len(due), 1)  # just d7 (unfired), not four daily notices

    def test_evaluate__renewal_re_arms_the_cadence(self):
        """Advancing paid_until (a renewal) re-arms the milestones via the new period_key."""
        deadline = TODAY + timedelta(days=20)
        self.set_deck(trial_end_date=None, paid_until=deadline)
        process_deck_notices(self.tenant)  # fires d30 for this deadline
        self.assertEqual(self.due(), [])

        renewed = deadline + timedelta(days=365)
        self.set_deck(paid_until=renewed)
        self.assertEqual(self.due(), [])  # renewed deadline is far away: quiet again

        with freeze_time("2027-08-10 20:00:00"):  # 25 days before the renewed deadline
            self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'd30', str(renewed))])

    def test_evaluate__limit_warnings_at_80_and_100_re_armed_monthly(self):
        """The 80% warning fires once per month; hitting 100% fires the stronger notice."""
        self.set_deck(active_user_count=4)  # trial cap is 5 -> 80%
        self.assertEqual(self.due(), [(DeckNotice.KIND_LIMIT, 'pct80', '2026-08')])
        process_deck_notices(self.tenant)
        self.assertEqual(self.due(), [])  # once this month

        self.set_deck(active_user_count=5)  # at the cap
        self.assertEqual(self.due(), [(DeckNotice.KIND_LIMIT, 'pct100', '2026-08')])

        with freeze_time("2026-09-15 20:00:00"):  # next month re-arms
            # push the trial deadline far out so its own d30 window doesn't co-fire here
            self.set_deck(active_user_count=4, trial_end_date=TODAY + timedelta(days=365))
            self.assertEqual(self.due(), [(DeckNotice.KIND_LIMIT, 'pct80', '2026-09')])

    def test_evaluate__unlimited_deck_gets_no_limit_warnings(self):
        """The -1 unlimited sentinel disables limit warnings entirely."""
        self.set_deck(max_active_users=-1, paid_until=TODAY + timedelta(days=90), active_user_count=999)
        self.assertEqual(self.due(), [])

    def test_evaluate__suspension_notice_once_per_episode(self):
        """A suspended deck gets exactly one suspension notice (keyed to the lapsed deadline),
        and no expiry cadence."""
        self.set_deck(trial_end_date=TODAY - timedelta(days=1), paid_until=None)
        self.assertEqual(self.due(), [(DeckNotice.KIND_SUSPENDED, 'suspended', str(TODAY - timedelta(days=1)))])
        process_deck_notices(self.tenant)
        self.assertEqual(self.due(), [])
        with freeze_time("2026-09-15 20:00:00"):
            self.assertEqual(self.due(), [])  # still just the one


@freeze_time(NOW)
class DeckNoticeDeliveryTest(ByteDeckTenantTestCase):
    """Delivery and rollout-gating tests for process_deck_notices (epic #1729 PR 5).

    The engine dispatches the owner email through send_email_message.apply_async;
    tests run celery non-eagerly, so delivery tests patch apply_async to execute
    the task inline and land the message in mail.outbox.
    """

    def run_engine_with_inline_email(self):
        """Run process_deck_notices with the email task executing synchronously."""
        from unittest.mock import patch

        from tenant import tasks

        with patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        ):
            return process_deck_notices(self.tenant)

    def setUp(self):
        """Put this deck at its 100% limit so exactly one notice is due, give the deck
        owner a primary email (the seeded owner has none), and clear caches."""
        from allauth.account.models import EmailAddress
        from siteconfig.models import SiteConfig

        cache.delete(deck_cache_key(self.tenant.schema_name))
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=TODAY + timedelta(days=60), paid_until=None, active_user_count=5)
        self.tenant.refresh_from_db()

        owner = SiteConfig.get().deck_owner
        if not owner.email:
            email_address = EmailAddress.objects.add_email(request=None, user=owner, email='owner@example.com')
            email_address.set_as_primary()
            email_address.save()
        # a secondary (non-primary) address, so owner-email resolution has to skip past it
        EmailAddress.objects.get_or_create(user=owner, email='owner-alt@example.com')

        # Give the deck a dedicated AI user, as properly-configured decks have. The
        # seeded tenant defaults deck_ai to the first staff user (= the owner), and
        # the notifications app skips self-notifications (recipient == sender), which
        # would silently drop the owner's in-app notice.
        from django.contrib.auth import get_user_model
        config = SiteConfig.get()
        if config.deck_ai == config.deck_owner:
            config.deck_ai = get_user_model().objects.create(username='deck_ai_bot', is_staff=True)
            config.save()

    def test_process__report_only_by_default_sends_and_records_nothing(self):
        """With DECK_NOTICES_ENABLED off (the default), the engine only reports."""
        summary = process_deck_notices(self.tenant)
        self.assertIn('REPORT-ONLY', summary)
        self.assertIn('limit/pct100', summary)
        self.assertFalse(DeckNotice.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__records_ledger_and_delivers_both_channels(self):
        """When enabled, a due notice writes its ledger row, emails the deck owner, and
        creates an in-app notification from the deck AI."""
        summary = self.run_engine_with_inline_email()
        self.assertIn('sent 1 notice(s)', summary)

        notice = DeckNotice.objects.get()
        self.assertEqual((notice.kind, notice.threshold), (DeckNotice.KIND_LIMIT, 'pct100'))

        # email went to the deck owner (send_email_message BCCs the recipient list)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('current-student limit warning', mail.outbox[0].subject)
        self.assertIn(self.tenant.get_owner_email_cached(), mail.outbox[0].bcc)
        self.assertIn('current', mail.outbox[0].body)  # vocabulary: current students

        # in-app notification exists for the deck owner
        from siteconfig.models import SiteConfig
        owner = SiteConfig.get().deck_owner
        self.assertTrue(Notification.objects.filter(recipient=owner, verb__contains='limit warning').exists())

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__second_run_sends_nothing_new(self):
        """Running the engine twice on the same day delivers exactly once."""
        self.run_engine_with_inline_email()
        summary = self.run_engine_with_inline_email()
        self.assertEqual(summary, 'no notices due')
        self.assertEqual(DeckNotice.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__concurrent_run_race_skips_delivery(self):
        """If another run records the ledger row between evaluation and get_or_create
        (a lost race), this run skips delivery instead of double-sending."""
        from unittest.mock import patch

        notice = (DeckNotice.KIND_LIMIT, 'pct100', '2026-08')
        DeckNotice.objects.create(tenant=self.tenant, kind=notice[0], threshold=notice[1], period_key=notice[2])
        # evaluation normally filters out recorded notices; force it to return the
        # already-recorded one, as if a concurrent run recorded it a moment after
        with patch('tenant.notices.evaluate_deck_notices', return_value=[notice]):
            summary = self.run_engine_with_inline_email()
        self.assertIn('sent 0 notice(s)', summary)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__failed_delivery_rolls_back_ledger_so_next_run_retries(self):
        """If delivery raises after the ledger write, the row rolls back (and no email
        is queued -- the enqueue is sequenced after the in-app notification), so the
        notice isn't recorded-but-never-sent: the next run retries."""
        from unittest.mock import patch

        with patch('tenant.notices.notify.send', side_effect=RuntimeError('notification backend down')):
            with self.assertRaises(RuntimeError):
                process_deck_notices(self.tenant)
        self.assertFalse(DeckNotice.objects.exists())  # rolled back, eligible for retry
        self.assertEqual(len(mail.outbox), 0)  # enqueue never reached

        # the next (healthy) run delivers normally
        self.run_engine_with_inline_email()
        self.assertEqual(DeckNotice.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__broker_failure_rolls_back_ledger_and_notification(self):
        """If the email enqueue itself fails (broker down), the ledger row AND the
        in-app notification roll back together, so the next run retries the whole
        notice instead of leaving it recorded with the email never handed off."""
        from unittest.mock import patch

        from siteconfig.models import SiteConfig
        from tenant import tasks

        owner = SiteConfig.get().deck_owner
        with patch.object(tasks.send_email_message, 'apply_async', side_effect=RuntimeError('broker down')):
            with self.assertRaises(RuntimeError):
                process_deck_notices(self.tenant)
        self.assertFalse(DeckNotice.objects.exists())  # rolled back, eligible for retry
        notice_notifications = Notification.objects.filter(recipient=owner, verb__contains='limit warning')
        self.assertFalse(notice_notifications.exists())  # rolled back too

        # the next (healthy) run delivers both channels
        self.run_engine_with_inline_email()
        self.assertEqual(DeckNotice.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(notice_notifications.exists())

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__owner_without_email_still_gets_in_app_notification(self):
        """A deck whose owner has no known email skips the email channel but still
        records the notice and creates the in-app notification."""
        from allauth.account.models import EmailAddress
        from siteconfig.models import SiteConfig

        owner = SiteConfig.get().deck_owner
        EmailAddress.objects.filter(user=owner).delete()
        self.assertIsNone(self.tenant.get_owner_email_cached())

        summary = self.run_engine_with_inline_email()
        self.assertIn('sent 1 notice(s)', summary)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(Notification.objects.filter(recipient=owner, verb__contains='limit warning').exists())
