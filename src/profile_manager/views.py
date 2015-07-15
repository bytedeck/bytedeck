from django.shortcuts import render, get_object_or_404
from django.template import RequestContext, loader
from .forms import ProfileForm
from .models import Profile
from django.http import HttpResponse

# Create your views here.
def profile(request):
    if request.user.is_authenticated: #this doesn't seemt o be working...
        p = get_object_or_404(Profile, user=request.user)
        context = {
            "title": "Profile",
            "heading": ("Profile of %s" % request.user),
            "p": p,
        }
        return render(request, 'profile_manager/detail.html', context)
    else:
        return render(request, "home.html", {})
