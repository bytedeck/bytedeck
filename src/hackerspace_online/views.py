from django.http import Http404
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required

from courses.models import Semester
from tenant.views import allow_non_public_view


@allow_non_public_view
def home(request):
    if request.user.is_staff:
        return redirect('quests:approvals')

    if request.user.is_authenticated:
        return redirect('quests:quests')

    return render(request, "home.html", {})


@allow_non_public_view
def simple(request):
    return render(request, "secret.html", {})
