from django.shortcuts import render, redirect
# from .forms import HackerspaceConfigForm


def home(request):
    if request.user.is_staff:
        return redirect('quests:approvals')

    if request.user.is_authenticated:
        return redirect('quests:quests')

    return render(request, "home.html", {})


def simple(request):
    return render(request, "secret.html", {})
