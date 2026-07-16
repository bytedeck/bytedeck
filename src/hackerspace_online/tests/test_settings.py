from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase

from hackerspace_online.settings import _validate_deployment_settings


class SecureProxySSLHeaderTest(SimpleTestCase):
    """The app runs behind an nginx/uWSGI front end that terminates TLS and
    forwards to Django over plain HTTP, so Django must trust the forwarded scheme
    to recognize secure requests and build https:// URLs (e.g. in email links)."""

    def test_secure_proxy_ssl_header_is_configured(self):
        """SECURE_PROXY_SSL_HEADER must name the X-Forwarded-Proto header nginx sets."""
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_forwarded_https_request_is_secure(self):
        """A request forwarded with X-Forwarded-Proto: https is treated as secure,
        so build_absolute_uri produces https:// links instead of http://."""
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(request.is_secure())
        self.assertTrue(request.build_absolute_uri("/decks/request/new/").startswith("https://"))

    def test_forwarded_http_request_is_not_secure(self):
        """Without the https forwarded scheme, the request stays plain HTTP so the
        header can't be used to fake a secure request."""
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="http")
        self.assertFalse(request.is_secure())


class DeploymentSettingsGuardTest(SimpleTestCase):
    """A real (non-localhost) deployment must not boot with the shipped example
    defaults; `_validate_deployment_settings` raises to prevent it, while leaving
    local development untouched."""

    def test_local_development_is_never_blocked(self):
        """localhost is local dev, so the example DEBUG=True + default SECRET_KEY are allowed."""
        # Should not raise.
        _validate_deployment_settings("localhost", True, "Change.Me!")

    def test_real_deployment_rejects_debug_true(self):
        """DEBUG=True on a real domain is refused, so debug pages can't leak in production."""
        with self.assertRaises(ImproperlyConfigured):
            _validate_deployment_settings("bytedeck.com", True, "a-real-random-secret-key")

    def test_real_deployment_rejects_default_secret_key(self):
        """The example 'Change.Me!' SECRET_KEY is refused on a real domain."""
        with self.assertRaises(ImproperlyConfigured):
            _validate_deployment_settings("bytedeck.com", False, "Change.Me!")

    def test_properly_configured_deployment_is_allowed(self):
        """DEBUG=False with a unique SECRET_KEY on a real domain passes the guard."""
        # Should not raise.
        _validate_deployment_settings("bytedeck.com", False, "a-real-random-secret-key")


class DatabaseConnectionSettingsTest(SimpleTestCase):
    """Persistent DB connections (CONN_MAX_AGE) must be paired with connection
    health checks, otherwise a pooled connection that died while idle (RDS
    failover, network blip, server-side timeout) surfaces as an intermittent
    error on whatever request draws it."""

    def test_conn_health_checks_enabled(self):
        """CONN_HEALTH_CHECKS must be True so dead persistent connections are
        detected and transparently re-established at the start of a request."""
        self.assertTrue(settings.DATABASES["default"]["CONN_HEALTH_CHECKS"])


class EmailSettingsTest(SimpleTestCase):
    """EMAIL_FILE_PATH previously read the wrong environment variable
    (EMAIL_BACKEND, a copy-paste bug), so setting EMAIL_BACKEND would silently
    corrupt the file-based backend's output directory."""

    def test_email_file_path__defaults_to_sent_mail_dir(self):
        """EMAIL_FILE_PATH must be a filesystem path (the _sent_mail directory
        by default), never the value of the EMAIL_BACKEND setting."""
        self.assertTrue(settings.EMAIL_FILE_PATH.endswith("_sent_mail"))
        self.assertNotEqual(settings.EMAIL_FILE_PATH, settings.EMAIL_BACKEND)


class DataUploadLimitTest(SimpleTestCase):
    """DATA_UPLOAD_MAX_MEMORY_SIZE was previously unset, so Django's 2.5 MB
    default applied even though nginx allows 17 MB request bodies -- large
    non-file form posts tripped RequestDataTooBigMiddleware far below the
    intended cap."""

    def test_data_upload_limit__raised_above_django_default(self):
        """The explicit limit must be 16 MiB: above Django's 2.5 MB default and
        below nginx's 17 MB client_max_body_size."""
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 16 * 1024 * 1024)


class CelerySettingsTest(SimpleTestCase):
    """Worker-hardening settings for the single shared Celery worker: bound
    memory leaks, keep quick tasks from queueing behind long all-schema tasks,
    and kill hung tasks instead of losing a worker slot forever."""

    def test_results_ignored(self):
        """No result backend is configured and nothing reads task results, so
        results must be ignored rather than stored on the broker."""
        self.assertTrue(settings.CELERY_TASK_IGNORE_RESULT)

    def test_worker_recycling_enabled(self):
        """Workers must recycle after a bounded number of tasks so leaks from
        the per-schema fan-out tasks can't grow without limit."""
        self.assertGreater(settings.CELERY_WORKER_MAX_TASKS_PER_CHILD, 0)

    def test_prefetch_disabled_for_mixed_workload(self):
        """Prefetch multiplier must be 1 so seconds-long tasks don't get stuck
        prefetched behind minutes-long all-schema tasks."""
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)

    def test_time_limits_sane(self):
        """A soft limit must exist and fire before the hard kill so tasks get a
        chance to clean up (SoftTimeLimitExceeded) before the worker is killed."""
        self.assertLess(settings.CELERY_TASK_SOFT_TIME_LIMIT, settings.CELERY_TASK_TIME_LIMIT)

    def test_broker_retry_on_startup(self):
        """The worker must retry the broker connection at startup instead of
        dying if redis is momentarily slower to come up."""
        self.assertTrue(settings.CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP)
