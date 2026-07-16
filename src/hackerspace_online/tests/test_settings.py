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
