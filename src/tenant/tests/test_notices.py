from datetime import date, timedelta

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import override_settings

from freezegun import freeze_time

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification
from siteconfig.models import SiteConfig
from tenant.models import GRACE_PERIOD_DAYS, DeckNotice, Tenant
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

    def test_evaluate__expiry_key_uses_the_governing_trial_deadline(self):
        """With an in-grace paid date and a LATER governing trial date, the expiry
        notice is keyed to the governing trial deadline (the one the email
        reports), so milestones recorded under the stale paid key can never
        suppress reminders for the clock that actually governs (#1734 B4
        review find)."""
        trial = TODAY + timedelta(days=20)
        self.set_deck(trial_end_date=trial, paid_until=TODAY - timedelta(days=10))
        self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'd30', str(trial))])
        process_deck_notices(self.tenant)
        self.assertTrue(DeckNotice.objects.filter(
            tenant=self.tenant, kind=DeckNotice.KIND_EXPIRY, threshold='d30', period_key=str(trial)).exists())
        self.assertEqual(self.due(), [])  # recorded under the governing key: nothing more due

    def test_evaluate__suspension_notice_once_per_episode(self):
        """A suspended deck gets exactly one suspension notice (keyed to the lapsed deadline),
        and no expiry cadence. The trial must be lapsed past the unified grace
        window (#1734 B4) to be suspended at all."""
        lapsed = TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)
        self.set_deck(trial_end_date=lapsed, paid_until=None)
        self.assertEqual(self.due(), [(DeckNotice.KIND_SUSPENDED, 'suspended', str(lapsed))])
        process_deck_notices(self.tenant)
        self.assertEqual(self.due(), [])
        with freeze_time("2026-09-15 20:00:00"):
            self.assertEqual(self.due(), [])  # still just the one

    def test_evaluate__lapsed_trial_stays_on_expiry_cadence_through_grace(self):
        """A lapsed trial inside its grace window is NOT suspended: it stays on the
        expiry-reminder cadence (daily after the milestone), exactly like a lapsed
        paid deck (#1734 B4)."""
        lapsed = TODAY - timedelta(days=10)
        self.set_deck(trial_end_date=lapsed, paid_until=None)
        self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'd7', str(lapsed))])  # no suspension notice
        process_deck_notices(self.tenant)
        with freeze_time("2026-08-16 20:00:00"):
            self.assertEqual(self.due(), [(DeckNotice.KIND_EXPIRY, 'daily-2026-08-16', str(lapsed))])


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
        # the notification carries the notice's key fact and links the subscription
        # page (maintainer request, 2026-08-08: the bare label wasn't actionable)
        self.assertEqual(
            notification.verb,
            'sent a current-student limit warning: 5 of 5 current-student seats are used. See your')
        self.assertEqual(notification.target_url, reverse('decks:subscription'))
        self.assertEqual(notification.target_link_text, 'subscription details page.')

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
        self.assertIn('Bytedeck sent a current-student limit warning:', notification.get_link())

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
    def test_deliver__notification_names_the_governing_deadline(self):
        """The expiry notification names the governing clock's deadline while it
        approaches, switches to the grace-window wording once it has passed, and
        the suspended notice adds the deletion horizon: the owner sees the date
        that matters without opening the email (maintainer request, 2026-08-08)."""
        from unittest.mock import patch

        from django.urls import reverse

        from siteconfig.models import SiteConfig
        from tenant import tasks
        from tenant.notices import _deliver

        owner = SiteConfig.get().deck_owner
        inline_email = patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        )

        # approaching: trial ends Aug 22 (7 days from frozen TODAY Aug 15)
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=TODAY + timedelta(days=7), paid_until=None)
        self.tenant.refresh_from_db()
        with inline_email:
            _deliver(self.tenant, DeckNotice.KIND_EXPIRY)
        notification = Notification.objects.filter(recipient=owner).latest('id')
        self.assertEqual(
            notification.verb,
            "sent a subscription expiry reminder: this deck's free trial ends on Aug. 22, 2026 (7 days left). See your")
        self.assertEqual(notification.target_url, reverse('decks:subscription'))

        # lapsed into grace: ended Aug 10, grace runs to Sep 9 (30 days)
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=TODAY - timedelta(days=5))
        self.tenant.refresh_from_db()
        with inline_email:
            _deliver(self.tenant, DeckNotice.KIND_EXPIRY)
        notification = Notification.objects.filter(recipient=owner).latest('id')
        self.assertEqual(
            notification.verb,
            "sent a subscription expiry reminder: this deck's free trial ended on Aug. 10, 2026 "
            "and the grace period ends on Sept. 9, 2026. See your")

        # suspended: lapsed past the grace window; the deletion horizon is named
        # (warned today, so a year from frozen TODAY)
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1))
        self.tenant.refresh_from_db()
        with inline_email:
            _deliver(self.tenant, DeckNotice.KIND_SUSPENDED)
        notification = Notification.objects.filter(recipient=owner).latest('id')
        self.assertEqual(
            notification.verb,
            "sent a deck suspended warning: this deck's free trial ended on July 15, 2026 "
            "and the grace period has run out; without a subscription the deck may be "
            "deleted after Aug. 15, 2027. See your")

        # defensive fall-through: a deck with no running deletion clock (it isn't
        # actually suspended, so Tenant.deletion_date is None) still gets a
        # coherent sentence, just without the deletion clause
        from tenant.notices import _notification_detail
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=TODAY + timedelta(days=60))
        self.tenant.refresh_from_db()
        detail = _notification_detail(self.tenant, DeckNotice.KIND_SUSPENDED)
        self.assertNotIn('deleted after', detail)
        self.assertTrue(detail.endswith('the grace period has run out.'))

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
        """A deck whose owner has no email at all skips the email channel but still
        records the notice and creates the in-app notification."""
        from django.contrib.auth import get_user_model
        from siteconfig.models import SiteConfig

        owner = SiteConfig.get().deck_owner
        get_user_model().objects.filter(pk=owner.pk).update(email='')
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
        how many days remain -- plus current seat usage and the ByteDeck wordmark
        (settings.PUBLIC_EMAIL_LOGO_URL) that signs every platform email
        (maintainer request from staging live testing, 2026-07-25)."""
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
        self.assertIn('non-profit Society registered in British Columbia', html)  # every platform email carries the Society blurb
        self.assertIn('contact@bytedeck.com', html)  # ...and a contact address for questions
        self.assertIn(f'alt="[Logo]" src="{settings.PUBLIC_EMAIL_LOGO_URL}" width="255" height="64"', html)

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
    def test_deliver__limit_email_names_the_grace_state(self):
        """The limit email on an in-grace deck says the governing clock already
        ran out and the deck is in its grace period, rather than quoting a
        pre-lapse deadline (#1734 B5)."""
        from unittest.mock import patch

        from tenant import tasks
        from tenant.notices import _deliver

        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=TODAY - timedelta(days=5), paid_until=None,
            max_active_users=5, active_user_count=5)
        self.tenant.refresh_from_db()

        with patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        ):
            _deliver(self.tenant, DeckNotice.KIND_LIMIT)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('free trial ended on <strong>Aug. 10, 2026</strong> and the deck is in its grace period', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__suspended_email_states_when_and_why_with_logo(self):
        """The suspension email says when the suspension began, which clock ran
        out (trial or paid, plus the unified grace window, #1734 B4), current
        seat usage, and carries the logo."""
        from datetime import date

        Tenant.objects.filter(pk=self.tenant.pk).update(
            # trial ended Jul 1 + 30-day grace ended Jul 31 -> suspended Aug 1
            trial_end_date=date(2026, 7, 1), paid_until=None,
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
        # (maintainer decision, 2026-07-31; Tenant.deletion_date).
        self.assertIn('scheduled for deletion on Aug. 15, 2027', html)
        self.assertIn('365 days from now', html)
        self.assertIn(f'<a href="{self.tenant.get_root_url()}">', html)
        self.assertIn('since <strong>Aug. 1, 2026</strong>', html)
        self.assertIn('free trial ended on July 1, 2026', html)
        self.assertIn('grace period ended on July 31, 2026', html)
        # the new suspension rules (redesign, 2026-07-30): owner-only sign-in,
        # data intact, and the Maintenance escape hatch
        self.assertIn('only the deck owner can sign in', html)
        self.assertIn('your content and student data are intact', html)
        self.assertIn('<em>Maintenance</em> subscription', html)
        self.assertIn('non-profit Society registered in British Columbia', html)  # every platform email carries the Society blurb
        self.assertIn('contact@bytedeck.com', html)  # ...and a contact address for questions
        # billing emails are signed by the platform, never the deck (maintainer request, 2026-07-30)
        self.assertIn('<p>Bytedeck</p>', html)
        # ...and branded by the platform too: the ByteDeck wordmark at half its
        # natural size, by absolute URL, with the deck's own logo nowhere in the
        # message (maintainer request, 2026-08-10: a deck's logo belongs on the
        # mail that deck sends its own users, not on mail from Bytedeck)
        self.assertIn(f'alt="[Logo]" src="{settings.PUBLIC_EMAIL_LOGO_URL}" width="255" height="64"', html)
        self.assertNotIn(SiteConfig.get().get_site_logo_url(), html)
        # the Society note closes the email BENEATH the wordmark, and invites the
        # reader onto the board through a mailto (maintainer request, 2026-08-10)
        self.assertLess(html.index('alt="[Logo]"'), html.index('non-profit Society'))
        self.assertIn('awesome app?</em> <em><a href="mailto:contact@bytedeck.com">Contact us</a>!</em>', html)
        # the same separator in the PLAIN-TEXT part, which is what the split
        # emphasis run buys: html2text drops the space in front of a link that
        # sits inside an <em>, leaving text-only clients "awesome app?[Contact us]"
        plain_text = ' '.join(mail.outbox[0].body.split())
        self.assertIn('awesome app?_ _[Contact us](mailto:contact@bytedeck.com)!_', plain_text)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_process__suspended_email_follows_the_governing_trial_clock(self):
        """With BOTH dates set and the trial the LATER clock (an admin-extended
        trial on a deck whose paid period lapsed earlier), the suspension email
        explains the TRIAL clock: the governing deadline picks the wording, not
        whether a paid date exists (#1734 B4 review find)."""
        from datetime import date

        Tenant.objects.filter(pk=self.tenant.pk).update(
            # paid lapsed May 1; trial extended to Jul 1 -> grace ended Jul 31 -> suspended Aug 1
            trial_end_date=date(2026, 7, 1), paid_until=date(2026, 5, 1),
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()

        summary = self.run_engine_with_inline_email()
        self.assertEqual(len(mail.outbox), 1, summary)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('since <strong>Aug. 1, 2026</strong>', html)
        self.assertIn('free trial ended on July 1, 2026', html)
        self.assertIn('grace period ended on July 31, 2026', html)
        self.assertNotIn('paid through', html)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_deliver__expiry_email_follows_the_governing_trial_clock(self):
        """With BOTH dates set and the trial the LATER clock, the expiry
        reminder's grace-window variant reports the TRIAL date and wording
        (#1734 B4 review find)."""
        from unittest.mock import patch

        from tenant import tasks
        from tenant.notices import _deliver

        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=TODAY - timedelta(days=5), paid_until=TODAY - timedelta(days=100),
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()

        with patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        ):
            _deliver(self.tenant, DeckNotice.KIND_EXPIRY)
        html = ' '.join(mail.outbox[0].alternatives[0][0].split())
        self.assertIn('free trial ended on <strong>Aug. 10, 2026</strong>', html)
        self.assertIn('(5 days ago)', html)
        self.assertNotIn('subscription expired', html)

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
        from unittest.mock import patch

        from tenant import tasks
        from tenant.notices import _deliver

        inline_email = patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        )

        # suspended Aug 6 (paid through Jul 6 + 30-day grace), warned Aug 10. The
        # planted row carries the key the engine really writes: the lapsed
        # deadline itself (str(paid_until)), not the grace window's end.
        Tenant.objects.filter(pk=self.tenant.pk).update(
            trial_end_date=None, paid_until=TODAY - timedelta(days=40),
            max_active_users=5, active_user_count=0,
        )
        self.tenant.refresh_from_db()
        row = DeckNotice.objects.create(
            tenant=self.tenant, kind=DeckNotice.KIND_SUSPENDED, threshold='suspended',
            period_key=str(TODAY - timedelta(days=40)),
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


@freeze_time(NOW)
@override_settings(DECK_NOTICES_ENABLED=False)  # the close is enforcement: NOT gated by the notices rollout flag
class SuspensionSemesterCloseTest(ByteDeckTenantTestCase):
    """Tests for close_semester_on_new_suspension (#1734 redesign B2): a fresh
    suspension closes the deck's open semester exactly once per episode, returning
    awaiting-approval submissions first and clamping negative XP, so current
    students drop to zero."""

    def setUp(self):
        """Clear the cached deck row so each test reads its own billing state."""
        cache.delete(deck_cache_key(self.tenant.schema_name))

    def set_deck(self, **fields):
        """Persist billing fields via update() + refresh (the close reads the instance)."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def close(self):
        """Shorthand: run the semester close for this deck and return its log summary."""
        from tenant.notices import close_semester_on_new_suspension
        return close_semester_on_new_suspension(self.tenant)

    def test_close__fresh_suspension_closes_semester_once(self):
        """A fresh suspension returns the awaiting-approval submission (unblocking
        the close, which then sweeps it with the rest of the in-progress work, as
        any semester close does), closes the semester, and drops the
        current-student count to zero -- all with the notices flag off. The
        episode is recorded, so a second run is a no-op."""
        from django.contrib.auth import get_user_model
        from model_bakery import baker
        from quest_manager.models import QuestSubmission
        from siteconfig.models import SiteConfig

        User = get_user_model()
        baker.make(User, is_staff=True)  # a teacher must exist before students
        student = baker.make(User)
        baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        submission = baker.make(
            QuestSubmission, user=student, is_completed=True, is_approved=False,
            semester=SiteConfig.get().active_semester,
        )
        self.assertGreater(self.tenant.get_active_user_count(), 0)

        self.set_deck(trial_end_date=TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), paid_until=None)
        summary = self.close()
        self.assertIn('closed semester', summary)
        self.assertIn('returned 1 awaiting-approval submission(s)', summary)

        self.assertTrue(SiteConfig.get().active_semester.closed)
        self.assertEqual(self.tenant.get_active_user_count(), 0)
        # the returned submission was then swept by the close's normal
        # in-progress cleanup: nothing stays stuck in a teacher's queue
        self.assertFalse(QuestSubmission.objects.filter(pk=submission.pk).exists())

        self.assertEqual(self.close(), 'semester close already handled this episode')

    def test_close__no_op_paths(self):
        """Unsuspended decks are untouched (no ledger row); a suspended deck whose
        semester is already closed records the episode without changes."""
        from siteconfig.models import SiteConfig

        self.set_deck(trial_end_date=TODAY + timedelta(days=60), paid_until=None)
        self.assertEqual(self.close(), 'not suspended')
        self.assertFalse(DeckNotice.objects.filter(threshold='semester-close').exists())

        sem = SiteConfig.get().active_semester
        sem.closed = True
        sem.save()
        self.set_deck(trial_end_date=TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1))
        self.assertEqual(self.close(), 'semester was already closed')
        self.assertEqual(self.close(), 'semester close already handled this episode')

    def test_close__clamps_negative_xp_to_zero(self):
        """A student with a negative XP balance doesn't block the auto-close: the
        final XP is recorded as zero (maintainer decision, 2026-07-30)."""
        from unittest.mock import patch

        from django.contrib.auth import get_user_model
        from model_bakery import baker
        from courses.models import CourseStudent
        from siteconfig.models import SiteConfig

        User = get_user_model()
        baker.make(User, is_staff=True)
        student = baker.make(User)
        registration = baker.make(CourseStudent, user=student, semester=SiteConfig.get().active_semester)

        self.set_deck(trial_end_date=TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), paid_until=None)
        with patch('profile_manager.models.Profile.xp_per_course', return_value=-50):
            summary = self.close()
        self.assertIn('closed semester', summary)
        registration.refresh_from_db()
        self.assertEqual(registration.final_xp, 0)
        self.assertFalse(registration.active)

    def test_close__failed_close_rolls_back_the_episode_ledger(self):
        """If the close unexpectedly refuses (the defensive sentinel path), the
        episode's ledger row rolls back with it, so the next nightly run retries
        instead of recording a close that never happened."""
        from unittest.mock import patch

        from courses.models import Semester

        self.set_deck(trial_end_date=TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), paid_until=None)
        with patch.object(Semester.objects, 'complete_active_semester', return_value=Semester.QUEST_AWAITING_APPROVAL):
            with self.assertRaises(RuntimeError):
                self.close()
        self.assertFalse(DeckNotice.objects.filter(threshold='semester-close').exists())
