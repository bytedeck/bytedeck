from django.utils.decorators import method_decorator
from django.contrib.auth import settings
from django.shortcuts import render, redirect, reverse


def staff_member_required(f):
    """
        Asserts if user is logged in and is_staff=True, if not redirects to 403 page or non admin login
        functionally the same as django.decorator.staff_member_required but this redirects to 403 page
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{reverse(settings.LOGIN_URL)}?next={request.path}')

        elif request.user.is_authenticated and request.user.is_staff:
            return f(request, *args, **kwargs)

        return render(request, '403.html', status=403)

    return wrapper


def xml_http_request_required(f):
    """
    Ensures that the request accessing the view is an ajax request.

    According to django docs:
        The HttpRequest.is_ajax() method is deprecated as it relied on a jQuery-specific way of signifying AJAX calls
        ...
        If you are writing your own AJAX detection method, request.is_ajax() can be reproduced exactly
        as request.headers.get('x-requested-with') == 'XMLHttpRequest'.
    """
    def wrapper(request, *args, **kwargs):
        if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return f(request, *args, **kwargs)
        return render(request, '403.html', status=403)

    return wrapper


class StaffMemberRequiredMixin:

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
