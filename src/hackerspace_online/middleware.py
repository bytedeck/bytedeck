from django.db import connections


class ForceDebugCursorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Enable database logging.
        connections['default'].force_debug_cursor = True
        response = self.get_response(request)
        return response
