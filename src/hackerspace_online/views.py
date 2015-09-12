from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test

from .settings import local

# @user_passes_test(lambda user: not user.get_username(), login_url='/quests', redirect_field_name=None)
def home(request):

    if request.user.is_staff:
        return redirect('quests:approvals')

    if request.user.is_authenticated():
        return redirect('quests:quests')

    return render(request, "home.html", {})
