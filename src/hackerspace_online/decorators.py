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

    
class StaffMemberRequiredMixin:

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
