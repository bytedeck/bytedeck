from django.core import mail

from django_tenants.test.cases import TenantTestCase

from tenant import tasks


class TenantTasksTests(TenantTestCase):
    """ Run tasks (from tenant module) asyncronously with apply() """

    def test_send_email_message(self):
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


class ClearExpiredSessionsTaskTest(TenantTestCase):
    """clear_expired_sessions_in_all_schemas purges expired django_session rows
    in every schema. Sessions are db-backed with an 8-week cookie age and
    nothing else runs clearsessions, so without this task the per-schema
    session tables grow forever."""

    def _make_session(self, key, expired):
        """Create a session row in the current schema, expired or not."""
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
