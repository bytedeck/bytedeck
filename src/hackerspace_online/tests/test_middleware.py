from functools import wraps

from django.conf import settings
from django.db import connections
from django.urls import reverse, path
from django.contrib.messages import get_messages
from django.test import override_settings, RequestFactory, SimpleTestCase
from django.http import HttpResponse

from django_tenants.test.client import TenantClient

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from hackerspace_online.middleware import ForceDebugCursorMiddleware
from hackerspace_online.urls import urlpatterns as hackerspace_urlpatterns


def without_requestdatatoobig_middleware(func):
    """
    Decorator for disabling hackerspace_online.middleware.RequestDataTooBigMiddleware, for testing purpose.
    """
    middleware = list(settings.MIDDLEWARE[:])
    middleware.remove("hackerspace_online.middleware.RequestDataTooBigMiddleware")

    @wraps(func)
    def _wrapped(*args, **kwargs):
        with override_settings(MIDDLEWARE=middleware):
            return func(*args, **kwargs)

    return _wrapped


def get_response_empty(request):
    """ returns an empty response, for testing purpose """

    # trying to process post and files, RequestDataTooBig exception will raises if
    # request body exceeded settings.DATA_UPLOAD_MAX_MEMORY_SIZE.
    request._load_post_and_files()
    return HttpResponse()


urlpatterns = [
    path("empty", get_response_empty, name="empty"),
] + hackerspace_urlpatterns


class RequestDataTooBigMiddlewareTestCase(ByteDeckTenantTestCase):
    """
    Various tests for `hackerspace_online.middleware.RequestDataTooBigMiddleware` class
    """

    def setUp(self):
        """Use a tenant client and ensure RequestDataTooBigMiddleware is enabled."""
        self.client = TenantClient(self.tenant)

        # make sure RequestDataTooBig middleware is enabled for a testing purpose
        self.old_MIDDLEWARE = settings.MIDDLEWARE
        middleware_class = "hackerspace_online.middleware.RequestDataTooBigMiddleware"
        if middleware_class not in settings.MIDDLEWARE:
            settings.MIDDLEWARE = list(settings.MIDDLEWARE) + [middleware_class]

    def tearDown(self):
        """Restore the original MIDDLEWARE setting after each test."""
        settings.MIDDLEWARE = self.old_MIDDLEWARE

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=2621440, ROOT_URLCONF=__name__)
    def test_default__passes_request_through(self):
        """
        By default request should pass through middleware as-is, without exceptions.
        """
        data = {"orson": "wells"}  # request data

        response = self.client.post(reverse("empty"), data=data)
        # should receive an empty response (ok) as if nothing has happened
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    @without_requestdatatoobig_middleware
    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=8, ROOT_URLCONF=__name__)
    def test_request_data_too_big__without_middleware_returns_400(self):
        """
        Somehow request data exceeds the settings.DATA_UPLOAD_MAX_MEMORY_SIZE limit,
        that raises `RequestDataTooBig` exception.

        Returns BadRequest (400), because `RequestDataTooBig` exception is not handled properly.
        """
        data = {"orson": "wells"}  # request data

        response = self.client.post(reverse("empty"), data=data)
        # should receive an bad request error (400) as request exceeds the limit.
        self.assertEqual(response.status_code, 400)
        # check for messages on a response that has no context
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 0)  # nothing, cuz not handled properly

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=8, ROOT_URLCONF=__name__)
    def test_request_data_too_big__with_middleware_redirects(self):
        """
        Somehow request data exceeds the settings.DATA_UPLOAD_MAX_MEMORY_SIZE limit,
        that raises `RequestDataTooBig` exception.

        Custom middleware should handle exception gracefully.
        """
        data = {"orson": "wells"}  # request data

        response = self.client.post(reverse("empty"), data=data)
        # should redirect back with error message (via django.contrib.messages framework)
        self.assertEqual(response.status_code, 302)
        # check for messages on a response that has no context
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)  # bingo!
        self.assertIn("requests exceeds the maximum size", str(messages[0]))

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=8, ROOT_URLCONF=__name__)
    def test_request_data_too_big__with_middleware_skips_files(self):
        """
        Custom middleware should handle uploaded files gracefully by simply skipping them
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        # trying to upload the file...
        f = SimpleUploadedFile("file.txt", b"lorem ipsum dolor sit amet..", content_type="text/plain")
        response = self.client.post(reverse("empty"), data={"file": f}, format="multipart")
        # should receive an empty response (ok) as if nothing has happened
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")


class ForceDebugCursorMiddlewareTestCase(SimpleTestCase):
    """Tests for `hackerspace_online.middleware.ForceDebugCursorMiddleware`, which forces the
    default DB connection's debug cursor on so queries get logged (enabled only when DEBUG)."""

    def test_call__enables_force_debug_cursor_and_returns_response(self):
        """Calling the middleware turns on the default connection's debug cursor and returns get_response's result."""
        # restore the flag afterwards so this test can't leak state into others
        original = connections['default'].force_debug_cursor
        self.addCleanup(setattr, connections['default'], 'force_debug_cursor', original)
        connections['default'].force_debug_cursor = False

        expected_response = HttpResponse()
        middleware = ForceDebugCursorMiddleware(get_response=lambda request: expected_response)

        result = middleware(RequestFactory().get('/'))

        self.assertIs(result, expected_response)
        self.assertTrue(connections['default'].force_debug_cursor)
