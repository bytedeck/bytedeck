from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Badge

@login_required
def list(request):

    badges = Badge.objects.all()

    context = {
        "heading": "Achievements",
        "badges": badges,
    }
    return render(request, "badges/list.html" , context)
