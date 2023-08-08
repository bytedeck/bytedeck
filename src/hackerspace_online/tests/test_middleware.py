from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse

from hackerspace_online.middleware import RequestDataTooBigMiddleware


def get_response_empty(request):
    """Returns an empty response, for testing purpose"""
    return HttpResponse()


class RequestDataTooBigMiddlewareTestCase(TestCase):
    """
    Various tests for `hackerspace_online.middleware.RequestDataTooBigMiddleware` class
    """

    def setUp(self):
        self.rf = RequestFactory()

    def test_default(self):
        """
        By default request should pass through middleware as-is, without exceptions.
        """
        data = b"""{"orson": "wells"}"""  # request data

        mw = RequestDataTooBigMiddleware(get_response_empty)
        request = self.rf.request(
            **{
                "wsgi.input": BytesIO(data),
                "CONTENT_LENGTH": len(data),
            }
        )

        # should receive an empty response as if nothing has happened
        response = mw(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=2, ALLOWED_HOSTS="*")
    @patch("hackerspace_online.middleware.messages.add_message")
    def test_request_data_too_big_exception(self, mock_add_message):
        """
        Somehow request data exceeds the settings.DATA_UPLOAD_MAX_MEMORY_SIZE limit,
        that raises `RequestDataTooBig` exception.

        Custom middleware should handle exception gracefully.
        """
        data = b"""{"orson": "wells"}"""  # request data

        mw = RequestDataTooBigMiddleware(get_response_empty)
        request = self.rf.request(
            **{
                "wsgi.input": BytesIO(data),
                "CONTENT_LENGTH": len(data),
            }
        )

        # should redirect back with error message
        response = mw(request)
        self.assertEqual(response.status_code, 302)
        mock_add_message.assert_called
