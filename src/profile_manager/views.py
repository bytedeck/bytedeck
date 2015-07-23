# from django.http import HttpResponse
# from django.template import RequestContext, loader
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic import DetailView, ListView
# from django.shortcuts import render, get_object_or_404

from .forms import ProfileForm
from .models import Profile
# Create your views here.

class ProfileList(ListView):
    model = Profile
    template_name = 'profile_manager/profile_list.html'

class ProfileCreate(CreateView):
    model = Profile
    form_class = ProfileForm
    template_name = 'profile_manager/form.html'

    def form_valid(self, form):
        data = form.save(commit=False)
        data.user = self.request.user
        data.save()
        return super(ProfileCreate, self).form_valid(form)

class ProfileDetail(DetailView):
    model = Profile

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileDetail, self).dispatch(*args, **kwargs)

class ProfileUpdate(UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = 'profile_manager/form.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileUpdate, self).dispatch(*args, **kwargs)
