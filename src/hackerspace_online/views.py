from django.shortcuts import render


def announcements(request):
    return render(request, "announcements.html", {})


def quests(request):
    return render(request, "quests.html", {})


def achievements(request):
    return render(request, "achievements.html", {})

def profile(request):
     return render(request, "profile", {})
