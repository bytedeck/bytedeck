from django.shortcuts import render
from django.views.generic import ListView

from .models import Announcement

# Create your views here.
class List(ListView):
    model = Announcement
    template_name = 'announcements/list.html'
