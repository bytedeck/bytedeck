from django.shortcuts import render
from .models import VideoResource
# from .forms import VideoForm


def videos(request):
    lastvideo = VideoResource.objects.last()

    video_file = lastvideo.video_file

    # form = VideoForm(request.POST or None, request.FILES or None)
    # if form.is_valid():
    #     form.save()

    context = {'video_file': video_file,
               'heading': "Video Resources"
               # 'form': form
               }

    return render(request, 'utilities/videos.html', context)
