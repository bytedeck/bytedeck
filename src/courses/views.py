from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic import DetailView, ListView
from django.shortcuts import get_object_or_404, redirect

# from .forms import ProfileForm
from .models import CourseStudent
from .forms import CourseStudentForm
# Create your views here.

class CourseStudentList(ListView):
    model = CourseStudent

class CourseStudentCreate(CreateView):
    model = CourseStudent
    # form_class = CourseStudentForm
    fields = ['semester', 'block', 'course', 'grade']
    success_url = reverse_lazy('quests:quests')

    # def get_initial(self):
    #     data = { 'user': self.request.user }
    #     return data

    def form_valid(self, form):
        form.instance.user = self.request.user
        # data = form.save(commit=False)
        # data.user = self.request.user
        # data.save()
        return super(CourseStudentCreate, self).form_valid(form)
#
# class ProfileDetail(DetailView):
#     model = UserCourse
#
#     @method_decorator(login_required)
#     def dispatch(self, *args, **kwargs):
#         # only allow the users to see their own profiles, or admins
#         profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
#         if profile_user == self.request.user or self.request.user.is_staff:
#             return super(ProfileDetail, self).dispatch(*args, **kwargs)
#
#         return redirect('quests:quests')

# class ProfileUpdate(UpdateView):
#     model = Profile
#     form_class = ProfileForm
#     template_name = 'profile_manager/form.html'
#
#     def get_context_data(self, **kwargs):
#         # Call the base implementation first to get a context
#         context = super(ProfileUpdate, self).get_context_data(**kwargs)
#         context['heading'] = "Edit " + self.request.user.get_username() +"'s Profile"
#         context['action_value']= ""
#         context['submit_btn_value']= "Update"
#         return context
#
#     def get_object(self):
#         return get_object_or_404(Profile, user_id=self.request.user)
#
#     @method_decorator(login_required)
#     def dispatch(self, *args, **kwargs):
#         profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
#         if profile_user == self.request.user or self.request.user.is_staff:
#             return super(ProfileUpdate, self).dispatch(*args, **kwargs)
#         return redirect('quests:quests')
