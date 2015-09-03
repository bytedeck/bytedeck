from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic import DetailView, ListView
from django.shortcuts import get_object_or_404, redirect

from courses.models import CourseStudent
from quest_manager.models import QuestSubmission
from badges.models import BadgeAssertion

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

    @method_decorator(login_required)
    def form_valid(self, form):
        data = form.save(commit=False)
        data.user = self.request.user
        data.save()
        return super(ProfileCreate, self).form_valid(form)


class ProfileDetail(DetailView):
    model = Profile

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        # only allow the users to see their own profiles, or admins
        profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
        if profile_user == self.request.user or self.request.user.is_staff:
            return super(ProfileDetail, self).dispatch(*args, **kwargs)

        return redirect('quests:quests')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
        context = super(ProfileDetail, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        # in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
        # completed_submissions = QuestSubmission.objects.all_completed(request.user)

        context['courses'] = CourseStudent.objects.all_for_user(profile_user)
        context['in_progress_submissions'] = QuestSubmission.objects.all_not_completed(profile_user)
        context['completed_submissions'] = QuestSubmission.objects.all_completed(profile_user)
        context['badge_assertions_by_type'] = BadgeAssertion.objects.get_by_type_for_user(profile_user)
        return context

class ProfileUpdate(UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = 'profile_manager/form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ProfileUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Edit " + self.request.user.get_username() +"'s Profile"
        context['action_value']= ""
        context['submit_btn_value']= "Update"
        return context

    def get_object(self):
        return get_object_or_404(Profile, user_id=self.request.user)

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
        if profile_user == self.request.user or self.request.user.is_staff:
            return super(ProfileUpdate, self).dispatch(*args, **kwargs)
        return redirect('quests:quests')
