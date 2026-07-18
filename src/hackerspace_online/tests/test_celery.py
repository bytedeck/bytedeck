from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase

from hackerspace_online.celery import app, email_admins_on_task_failure


class FakeTask:
    """Stand-in for the celery task object passed as `sender` to task_failure."""

    def __init__(self, name):
        """Store the dotted task name the handler reads off the sender.

        Args:
            name (str): value for the `name` attribute, mirroring a real
                celery task's registered name.
        """
        self.name = name


class EmailAdminsOnTaskFailureTest(SimpleTestCase):
    """The task_failure handler is the only visibility we have into celery task
    exceptions (no retries, no result backend, results ignored), so it must
    email ADMINS -- throttled so a failing fan-out can't send hundreds of
    emails, and without ever raising itself."""

    def setUp(self):
        """Each test starts with an empty throttle cache."""
        cache.clear()

    def _fire(self, task_name="app.tasks.some_task", exception=None):
        """Invoke the handler the way celery's task_failure signal would.

        Args:
            task_name (str): name given to the FakeTask sender.
            exception (Exception | None): exception to report; defaults to a
                ValueError.

        Returns None; assertions inspect mail.outbox afterwards.
        """
        email_admins_on_task_failure(
            sender=FakeTask(task_name),
            task_id="abc-123",
            exception=exception or ValueError("boom"),
            einfo="traceback goes here",
        )

    def test_task_failure__emails_admins(self):
        """A task failure sends one email naming the task and exception."""
        self._fire()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("app.tasks.some_task", mail.outbox[0].subject)
        self.assertIn("ValueError", mail.outbox[0].body)

    def test_task_failure__throttles_repeat_failures(self):
        """A second identical failure within the throttle window sends nothing."""
        self._fire()
        self._fire()
        self.assertEqual(len(mail.outbox), 1)

    def test_task_failure__different_exception_type_not_throttled(self):
        """A different exception type for the same task is a distinct alert."""
        self._fire(exception=ValueError("boom"))
        self._fire(exception=KeyError("boom"))
        self.assertEqual(len(mail.outbox), 2)

    def test_task_failure__sender_without_name(self):
        """A sender with no usable name falls back to repr() instead of crashing."""
        email_admins_on_task_failure(
            sender=None, task_id="abc", exception=ValueError("x"), einfo=""
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_task_failure__never_raises_when_cache_is_down(self):
        """If the throttle cache itself errors, the handler swallows it -- error
        reporting must not be able to take down the worker."""
        with patch("django.core.cache.cache.add", side_effect=RuntimeError("redis down")):
            self._fire()  # must not raise
        self.assertEqual(len(mail.outbox), 0)


class BeatScheduleTest(SimpleTestCase):
    """The session-cleanup task must actually be scheduled: DatabaseScheduler
    installs app.conf.beat_schedule entries as PeriodicTask rows on startup, so
    presence in the dict is what gets it running in production."""

    def test_clear_expired_sessions_scheduled(self):
        """The beat schedule includes the daily clearsessions fan-out task."""
        entry = app.conf.beat_schedule["Clear expired sessions in all schemas daily task"]
        self.assertEqual(entry["task"], "tenant.tasks.clear_expired_sessions_in_all_schemas")
