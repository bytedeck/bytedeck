from django.conf import settings
from django.db import connections
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.core.exceptions import RequestDataTooBig
from django.template.defaultfilters import filesizeformat


class ForceDebugCursorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Enable database logging.
        connections['default'].force_debug_cursor = True
        response = self.get_response(request)
        return response


class RequestDataTooBigMiddleware:
    """
    Custom middleware to handle requests that exceed the settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        If the request body is too big then request.body will throw a
        RequestDataTooBig exception. Check here explicitly if that will happen.
        """
        try:
            if request.method == 'POST':
                if request.content_type in ['', 'text/plain', 'application/json']:
                    # touch the body so that we have access to it in process_response
                    _ = request.body
                else:
                    _ = request.POST
        except RequestDataTooBig:
            # if the size of the request (excluding any file uploads) exceeded settings.DATA_UPLOAD_MAX_MEMORY_SIZE.
            msg = (
                f'This requests exceeds the maximum size of {filesizeformat(settings.DATA_UPLOAD_MAX_MEMORY_SIZE)}. This is likely caused by'
                ' one of the text fields contains too much data, either from text (including whitespace)'
                ' or a large data URI (an image or other data encoded as text).'
            )

            # generate a more sensible response and redirect back
            messages.add_message(request, messages.ERROR, msg)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        # ...as if nothing has happened
        return self.get_response(request)
