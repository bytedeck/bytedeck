from django.shortcuts import render
from django.views.generic import ListView
from django.views.generic.edit import CreateView

from .models import Announcement
from .forms import AnnouncementForm

# Create your views here.
class List(ListView):
    model = Announcement
    template_name = 'announcements/list.html'

class Create(CreateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form.html'

    def form_valid(self, form):
        data = form.save(commit=False)
        data.user = self.request.user
        data.save()
        return super(Create, self).form_valid(form)
