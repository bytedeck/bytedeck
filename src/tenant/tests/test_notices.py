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
@override_settings(DECK_NOTICES_ENABLED=False)  # the reset is enforcement: NOT gated by the notices rollout flag
class SuspensionCapResetTest(ByteDeckTenantTestCase):
    """Tests for reset_cap_on_new_suspension (#2178): when a suspension episode
    begins, the cap is written back to the trial default exactly once, and any
    admin adjustment afterwards -- lower or higher -- sticks."""

    def setUp(self):
        """Clear the cached deck row so each test reads its own billing state."""
        cache.delete(deck_cache_key(self.tenant.schema_name))

    def set_deck(self, **fields):
        """Persist billing fields via update() + refresh (the reset reads the instance)."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def reset(self):
        """Shorthand: run the reset for this deck and return its log summary."""
        from tenant.notices import reset_cap_on_new_suspension
        return reset_cap_on_new_suspension(self.tenant)

    def test_reset__fresh_suspension_reverts_cap_once_then_admin_wins(self):
        """A deck whose trial lapsed yesterday gets its cap written back to the
        trial default exactly once; an admin adjustment made afterwards (e.g.
        lowering to 1 for a wind-down, or raising for a comp) is never clobbered
        by later runs of the same episode."""
        self.set_deck(trial_end_date=TODAY - timedelta(days=1), paid_until=None, max_active_users=80)
        self.assertEqual(self.reset(), 'cap reset 80 -> 5')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 5)
        self.assertTrue(DeckNotice.objects.filter(tenant=self.tenant, threshold='cap-reset').exists())

        self.set_deck(max_active_users=1)  # admin wind-down after the reset
        self.assertEqual(self.reset(), 'cap already reset this episode')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 1)

    def test_reset__paid_deck_episode_starts_after_the_grace_window(self):
        """A paid deck's suspension episode begins the day after its grace window
        ends (paid_until + 30 + 1), so the reset fires on the task's first run
        after that day -- and -1 unlimited decks revert like any other."""
        self.set_deck(trial_end_date=None, paid_until=TODAY - timedelta(days=31), max_active_users=-1)
        self.assertEqual(self.reset(), 'cap reset -1 -> 5')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 5)

    def test_reset__old_episodes_are_grandfathered(self):
        """A deck already suspended for longer than the catch-up window keeps its
        cap (its admin may have hand-set it since -- the production case that
        motivated #2178); the episode is recorded so it is never revisited."""
        self.set_deck(trial_end_date=TODAY - timedelta(days=60), paid_until=None, max_active_users=1)
        self.assertIn('cap left alone', self.reset())
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 1)
        self.assertEqual(self.reset(), 'cap already reset this episode')

    def test_reset__no_op_paths(self):
        """Unsuspended decks are untouched (no ledger row), and a fresh suspension
        whose cap is already the trial default records the episode without a write."""
        self.set_deck(trial_end_date=TODAY + timedelta(days=60), paid_until=None, max_active_users=80)
        self.assertEqual(self.reset(), 'not suspended')
        self.assertFalse(DeckNotice.objects.filter(tenant=self.tenant, threshold='cap-reset').exists())

        self.set_deck(trial_end_date=TODAY - timedelta(days=1), max_active_users=5)
        self.assertEqual(self.reset(), 'cap already at the trial default')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 5)
        self.assertTrue(DeckNotice.objects.filter(tenant=self.tenant, threshold='cap-reset').exists())


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
        creates an in-app notification (sender choice has its own tests below)."""
        summary = self.run_engine_with_inline_email()
        self.assertIn('sent 1 notice(s)', summary)

        notice = DeckNotice.objects.get()
        self.assertEqual((notice.kind, notice.threshold), (DeckNotice.KIND_LIMIT, 'pct100'))

        # email went to the deck owner (send_email_message BCCs the recipient list)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('current-student limit warning', mail.outbox[0].subject)
        self.assertIn(self.tenant.get_owner_email_cached(), mail.outbox[0].bcc)
        self.assertIn('current', mail.outbox[0].body)  # vocabulary: current students
        # the subscribe link points at the deck's own subscription page (PR 6),
        # not the public flatpage
        from django.urls import reverse
        self.assertIn(self.tenant.get_root_url() + reverse('decks:subscription'), mail.outbox[0].body)

        # in-app notification exists for the deck owner, phrased as a complete
        # sentence: no dangling "for this deck:" pointing at an object that was
        # never attached (maintainer find, 2026-07-31)
        from siteconfig.models import SiteConfig
        owner = SiteConfig.get().deck_owner
        notification = Notification.objects.get(recipient=owner, verb__contains='limit warning')
        self.assertEqual(notification.verb, 'sent a current-student limit warning.')

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__notification_comes_from_support_admin_when_present(self):
        """The in-app notice's sender is the ByteDeck support account when the deck
        has one, so it renders as "Bytedeck sent a ..." instead of coming from a
        deck user's own account (maintainer request, 2026-07-31)."""
        from django.conf import settings
        from django.contrib.auth import get_user_model

        from siteconfig.models import SiteConfig

        support_admin, _ = get_user_model().objects.get_or_create(
            username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        self.run_engine_with_inline_email()

        owner = SiteConfig.get().deck_owner
        notification = Notification.objects.get(recipient=owner, verb__contains='limit warning')
        self.assertEqual(notification.sender_object, support_admin)
        self.assertIn('Bytedeck sent a current-student limit warning.', notification.get_link())

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__notification_sender_falls_back_to_deck_ai(self):
        """Decks without a usable support account (older decks predate it; here it
        is deactivated) still get their notice: the sender falls back to the deck
        AI user."""
        from django.conf import settings
        from django.contrib.auth import get_user_model

        from siteconfig.models import SiteConfig

        get_user_model().objects.filter(
            username=settings.TENANT_DEFAULT_ADMIN_USERNAME).update(is_active=False)
        self.run_engine_with_inline_email()

        owner = SiteConfig.get().deck_owner
        notification = Notification.objects.get(recipient=owner, verb__contains='limit warning')
        self.assertEqual(notification.sender_object, SiteConfig.get().deck_ai)

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

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__grace_period_email_states_suspension_ahead(self):
        """The grace-period expiry email tells the owner what follows the grace
        window: suspension, with only the deck owner able to sign in and the
        365-day deletion countdown starting (suspension redesign, 2026-07-30) --
        checked on the plain-text part, which must carry the same message."""
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=TODAY - timedelta(days=5),  # expired, in grace
            max_active_users=30, active_user_count=0,  # paid cap 30; no limit notice due
        )
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertIn('expiry', summary)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body.replace('\n', ' ')  # textify hard-wraps lines
        self.assertIn('grace period', body)
        self.assertIn('the deck will be suspended', body)
        self.assertIn('only the deck owner will be able to sign in', body)
        self.assertIn('365-day countdown to deck deletion', body)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__grace_email_includes_dates_seats_and_logo(self):
        """The grace-period expiry email states every date the owner needs -- when
        the subscription expired and how long ago, when the grace period ends and
        how many days remain -- plus current seat usage and the site logo
        (maintainer request from staging live testing, 2026-07-25: the old email
        gave no dates at all)."""
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=TODAY - timedelta(days=5),  # expired, in grace
            max_active_users=30, active_user_count=2,
        )
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertEqual(len(mail.outbox), 1, summary)
        html = mail.outbox[0].alternatives[0][0].replace('\n', ' ')
        self.assertIn('Aug. 10, 2026', html)   # expired on paid_until...
        self.assertIn('5 days ago', html)      # ...with the relative phrase
        self.assertIn('Sept. 9, 2026', html)   # grace ends paid_until + 30 days...
        self.assertIn('25 days left', html)    # ...with the countdown
        self.assertIn('using <strong>2</strong> of <strong>30</strong> current student', ' '.join(html.split()))
        self.assertIn('non-profit Society', html)  # every subscription email carries the Society blurb
        self.assertIn('contact@bytedeck.com', html)  # ...and a contact address for questions
        self.assertIn('alt="[Logo]"', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__comped_deck_limit_email_renders_without_any_dates(self):
        """A comped/managed-manually deck (both date fields blank, days_until_expiry
        None) can still hit its student cap; its limit email must render with no
        expiry dates to lean on -- covering the dateless arms of the new context."""
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=None, max_active_users=5, active_user_count=5)
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertIn('limit', summary)
        self.assertEqual(len(mail.outbox), 1)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('limit has been reached', html)
        self.assertIn('non-profit Society', html)  # every subscription email carries the Society blurb
        self.assertIn('contact@bytedeck.com', html)  # ...and a contact address for questions
        self.assertIn('alt="[Logo]"', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__suspended_email_states_when_and_why_with_logo(self):
        """The suspension email says when the suspension began, which clock ran
        out (trial vs paid + grace), current seat usage, and carries the logo."""
        from datetime import date

        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=date(2026, 8, 1), paid_until=None,  # trial lapsed -> suspended Aug 2
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertIn('suspended', summary)
        self.assertEqual(len(mail.outbox), 1, summary)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        # the bottom line LEADS (maintainer request, 2026-07-30): the scheduled
        # deletion date with the countdown, and the deck name links to the deck
        # itself. The deletion clock starts at the FIRST WARNING (this email,
        # sent on frozen TODAY Aug 15), never at the earlier lapse date
        # (maintainer decision, 2026-07-31).
        self.assertIn('scheduled for deletion on Aug. 15, 2027', html)
        self.assertIn('365 days from now', html)
        self.assertIn(f'<a href="{self.tenant.get_root_url()}">', html)
        self.assertIn('since <strong>Aug. 2, 2026</strong>', html)
        self.assertIn('free trial ended on Aug. 1, 2026', html)
        # the new suspension rules (redesign, 2026-07-30): owner-only sign-in,
        # data intact, and the Maintenance escape hatch
        self.assertIn('only the deck owner can sign in', html)
        self.assertIn('your content and student data are intact', html)
        self.assertIn('<em>Maintenance</em> subscription', html)
        self.assertIn('non-profit Society', html)  # every subscription email carries the Society blurb
        self.assertIn('contact@bytedeck.com', html)  # ...and a contact address for questions
        # billing emails are signed by the platform, never the deck (maintainer request, 2026-07-30)
        self.assertIn('<p>Bytedeck</p>', html)
        self.assertIn('alt="[Logo]"', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__suspended_email_paid_clock_and_legacy_full_year(self):
        """A deck suspended after a PAID subscription lapsed explains the paid
        clock (paid-through and grace-end dates) in its suspension email, with the
        bottom line carried by the plain-text part too. A LEGACY deck whose dates
        lapsed long before the notice machinery existed gets its full year from
        its first warning: no email can ever carry an already-passed deletion
        date (maintainer decision, 2026-07-31)."""
        # paid clock: paid through Jul 6, grace ends Aug 5 -> suspended Aug 6, 2026;
        # first warned on frozen TODAY (Aug 15) -> deletion Aug 15, 2027
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=TODAY - timedelta(days=40),
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertEqual(len(mail.outbox), 1, summary)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('subscription was paid through July 6, 2026', html)
        self.assertIn('grace period ended on Aug. 5, 2026', html)
        self.assertIn('scheduled for deletion on Aug. 15, 2027', html)
        self.assertIn('365 days from now', html)
        body = mail.outbox[0].body.replace('\n', ' ')  # textify hard-wraps lines
        self.assertIn('scheduled for deletion on Aug. 15, 2027', body)

        # legacy: suspended Aug 11, 2025 (400 days ago). Unclamped this deck's
        # deletion day would already be past; the warned-on clamp grants the full
        # year from today's first warning instead.
        mail.outbox.clear()
        Tenant.objects.filter(pk=self.tenant.pk).update(paid_until=TODAY - timedelta(days=400))
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertEqual(len(mail.outbox), 1, summary)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('since <strong>Aug. 11, 2025</strong>', html)  # the suspension date stays honest
        self.assertIn('scheduled for deletion on Aug. 15, 2027', html)
        self.assertIn('365 days from now', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_deliver__deletion_clock_runs_from_the_episodes_first_warning(self):
        """The deletion clock runs from the episode's FIRST warning: the suspended
        notice's ledger row is the durable warned-on record, so a deck warned days
        ago keeps that original clock, and with no ledger row yet the deck counts
        as warned today."""
        from datetime import date
        from unittest.mock import patch

        from tenant import tasks
        from tenant.notices import _deliver

        inline_email = patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        )

        # suspended Aug 6 (paid through Jul 6 + 30-day grace), warned Aug 10
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=TODAY - timedelta(days=40),
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()
        row = DeckNotice.objects.create(
            tenant=self.tenant, kind=DeckNotice.KIND_SUSPENDED, threshold='suspended',
            period_key=str(date(2026, 8, 5)),
        )
        # backdate past auto_now_add: the row records the warning sent on Aug 10
        DeckNotice.objects.filter(pk=row.pk).update(sent_on=date(2026, 8, 10))

        with inline_email:
            _deliver(self.tenant, DeckNotice.KIND_SUSPENDED)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('scheduled for deletion on Aug. 10, 2027', html)

        # no ledger row for the episode: treated as warned today (frozen Aug 15)
        mail.outbox.clear()
        DeckNotice.objects.all().delete()
        with inline_email:
            _deliver(self.tenant, DeckNotice.KIND_SUSPENDED)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('scheduled for deletion on Aug. 15, 2027', html)
