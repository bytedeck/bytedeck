from django.shortcuts import render, redirect

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
