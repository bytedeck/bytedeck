from django.conf import settings
from django.test import RequestFactory, SimpleTestCase


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
        self.assertTrue(request.build_absolute_uri("/decks/new/").startswith("https://"))

    def test_forwarded_http_request_is_not_secure(self):
        """Without the https forwarded scheme, the request stays plain HTTP so the
        header can't be used to fake a secure request."""
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="http")
        self.assertFalse(request.is_secure())
