from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test

def home(request):

    if request.user.is_staff:
        return redirect('quests:approvals')

    if request.user.is_authenticated():
        return redirect('quests:quests')

    return render(request, "home.html", {})
