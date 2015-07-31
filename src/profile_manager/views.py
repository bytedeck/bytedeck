# from django.http import HttpResponse
# from django.template import RequestContext, loader
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic import DetailView, ListView
from django.shortcuts import get_object_or_404

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

    def get_context_data(self, **kwargs):
        context = super(ProfileDetail, self).get_context_data(**kwargs)
        context['heading'] = self.request.user.username + "'s Profile"
        context
        return context

    def get_object(self):
        return get_object_or_404(Profile, user_id=self.request.user)

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileDetail, self).dispatch(*args, **kwargs)


class ProfileUpdate(UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = 'profile_manager/form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ProfileUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Edit " + self.request.user.username +"'s Profile"
        context['action_value']= ""
        context['submit_btn_value']= "Update"
        return context

    def get_object(self):
        return get_object_or_404(Profile, user_id=self.request.user)

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileUpdate, self).dispatch(*args, **kwargs)
