from django.shortcuts import render

from .models import VideoResource
from utilities.forms import VideoForm
from tenant.views import allow_non_public_view


@allow_non_public_view
def videos(request):
    videos = VideoResource.objects.all()
    form = VideoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
    context = {'videos': videos, 'heading': "Video Resources", 'form': form}
    return render(request, 'utilities/videos.html', context)
