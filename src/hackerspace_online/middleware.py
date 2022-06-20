from django.db import connections
from django.core.exceptions import PermissionDenied
from django.shortcuts import render


class ForceDebugCursorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Enable database logging.
        connections['default'].force_debug_cursor = True
        response = self.get_response(request)
        return response


# https://stackoverflow.com/a/68797100
class PermissionDeniedErrorHandler:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        # This is the method that responsible for the safe-exception handling
        if isinstance(exception, PermissionDenied):
            return render(
                request=request,
                template_name="403.html",
                status=403
            )
        return None
