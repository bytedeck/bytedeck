from django.core import mail

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from tenant import tasks


class TenantTasksTests(ByteDeckTenantTestCase):
    """ Run tasks (from tenant module) asyncronously with apply() """

    def test_send_email_message__delivers_to_recipients(self):
        """Async. task "send_email_message" sends email messages as expected."""
        # outbox is empty before executing the task
        self.assertEqual(len(mail.outbox), 0)

        # executing "send_email_message" task
        task_result = tasks.send_email_message.apply(
            kwargs={
                # subject, message and a list of recipients
                "subject": "O hi, World!",
                "message": "Lorem ipsum dolor sit amet...",
                "recipient_list": ["john@doe.com", "jane@doe.com"],
            }
        )
        self.assertTrue(task_result.successful())

        # email message was sent to multiple recipients
        self.assertEqual(len(mail.outbox), 1)  # expecting one email message
        self.assertEqual(mail.outbox[0].subject, "O hi, World!")
        # john doe was first in a list of recipients (BCC)
        self.assertIn("john@doe.com", mail.outbox[0].bcc)


class ClearExpiredSessionsTaskTest(ByteDeckTenantTestCase):
    """clear_expired_sessions_in_all_schemas purges expired django_session rows
    in every schema. Sessions are db-backed with an 8-week cookie age and
    nothing else runs clearsessions, so without this task the per-schema
    session tables grow forever."""

    def _make_session(self, key, expired):
        """Create a session row in the current schema, expired or not.

        Args:
            key (str): session_key for the new row (must be unique per schema).
            expired (bool): True dates the session one day in the past
                (eligible for clearsessions), False one day in the future.

        Returns:
            Session: the created django.contrib.sessions row.
        """
        from datetime import timedelta

        from django.contrib.sessions.models import Session
        from django.utils import timezone

        delta = timedelta(days=-1) if expired else timedelta(days=1)
        return Session.objects.create(
            session_key=key, session_data="x", expire_date=timezone.now() + delta
        )

    def test_clear_expired_sessions_in_all_schemas__purges_only_expired(self):
        """Expired sessions are deleted in both the tenant and public schemas;
        unexpired sessions survive."""
        from django.contrib.sessions.models import Session

        from django_tenants.utils import schema_context

        self._make_session("tenant-expired", expired=True)
        self._make_session("tenant-valid", expired=False)
        with schema_context("public"):
            self._make_session("public-expired", expired=True)
            self._make_session("public-valid", expired=False)

        task_result = tasks.clear_expired_sessions_in_all_schemas.apply()
        self.assertTrue(task_result.successful())

        self.assertFalse(Session.objects.filter(session_key="tenant-expired").exists())
        self.assertTrue(Session.objects.filter(session_key="tenant-valid").exists())
        with schema_context("public"):
            self.assertFalse(Session.objects.filter(session_key="public-expired").exists())
            self.assertTrue(Session.objects.filter(session_key="public-valid").exists())


class DeckStatusCheckTaskTests(ByteDeckTenantTestCase):
    """The nightly deck-status fan-out is the canonical refresher for the Tenant
    cached fields now that the admin changelist no longer refreshes them on page
    load (the old N+1). Dispatcher excludes the public and shared-library schemas."""

    def test_deck_status_check__refreshes_cached_fields(self):
        """Running the per-schema task updates the deck's stale cached counts."""
        from django.contrib.auth import get_user_model
        from model_bakery import baker
        from siteconfig.models import SiteConfig
        from tenant.models import Tenant

        User = get_user_model()
        student = baker.make(User)
        baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        Tenant.objects.filter(schema_name=self.tenant.schema_name).update(active_user_count=0)

        task_result = tasks.deck_status_check.apply()
        self.assertTrue(task_result.successful())

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.active_user_count, self.tenant.get_active_user_count())
        self.assertGreater(self.tenant.active_user_count, 0)

    def test_daily_deck_status_check_for_all_tenants__dispatches_only_billable_decks(self):
        """The dispatcher schedules one per-schema check per deck, skipping the
        public schema and the shared-library tenant."""
        from unittest.mock import patch

        from django_tenants.utils import get_public_schema_name, schema_context
        from library.utils import get_library_schema_name
        from tenant.models import Tenant

        billable_count = Tenant.objects.exclude(
            schema_name__in=[get_public_schema_name(), get_library_schema_name()]
        ).count()

        # a library tenant row (schema-less: fast, and the dispatcher must skip
        # it before ever entering its context) must not add a dispatch
        if not Tenant.objects.filter(schema_name=get_library_schema_name()).exists():
            with schema_context(get_public_schema_name()):
                library_tenant = Tenant(name=get_library_schema_name(), schema_name=get_library_schema_name())
                library_tenant.auto_create_schema = False
                library_tenant.full_clean()
                library_tenant.save()

        with patch.object(tasks.deck_status_check, 'apply_async') as mock_apply_async:
            task_result = tasks.daily_deck_status_check_for_all_tenants.apply()

        self.assertTrue(task_result.successful())
        self.assertEqual(mock_apply_async.call_count, billable_count)
        self.assertIn(f"for {billable_count} deck(s)", task_result.result)
