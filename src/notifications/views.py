from django.shortcuts import render

from .models import Notification
# Create your views here.

def list(request):
    notifications = Notification.objects.all_for_user(request.user)
    context = {
        "notifications": notifications,
    }
    return render(request, "notifications/list.html", context)
