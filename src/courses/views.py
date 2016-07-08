import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.core.urlresolvers import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic import DetailView, ListView
from django.shortcuts import get_object_or_404, redirect, render, Http404, HttpResponse

# from .forms import ProfileForm
from .models import CourseStudent, Rank
from .forms import CourseStudentForm
# Create your views here.

@login_required
def mark_calculations(request):
    template_name='courses/mark_calculations.html'
    course_student = CourseStudent.objects.current_course(request.user)
    courses = CourseStudent.objects.current_courses(request.user)
    num_courses = courses.count()
    if courses:
        xp_per_course = course_student.user.profile.xp()/courses.count()
    else:
        xp_per_course = None


    context = {
        'obj': course_student,
        'courses': courses,
        'xp_per_course': xp_per_course,
        'num_courses' : num_courses,
    }
    return render(request, template_name, context)


class RankList(ListView):
    model = Rank

class CourseStudentList(ListView):
    model = CourseStudent

@staff_member_required
def add_course_student(request, user_id):

    initial={}
    if int(user_id) > 0:
        user = get_object_or_404(User, pk=user_id)
    else:
        user = None

    form = CourseStudentForm(request.POST or None)

    if form.is_valid():
        new_course_student = form.save(commit=False)
        new_course_student.user = user
        new_course_student.save()
        # messages.success(request, ("Badge " + str(new_assertion) + " granted to " + str(new_assertion.user)))
        return redirect('profiles:profile_detail', pk = user.id)

    context = {
        "user": user,
        "form": form,
    }
    return render(request, 'courses/coursestudent_form.html', context)

class CourseStudentCreate(SuccessMessageMixin, CreateView):
    model = CourseStudent
    form_class = CourseStudentForm
    # fields = ['semester', 'block', 'course', 'grade']
    success_url = reverse_lazy('quests:quests')
    success_message = "You have been added to the %(course)s %(grade)s course"

    def get_form_kwargs(self):
        kwargs = super(CreateView, self).get_form_kwargs()
        kwargs['instance'] = CourseStudent(user=self.request.user)
        return kwargs


    # def get_initial(self):
    #     data = { 'user': self.request.user }
    #     return data

    # def form_valid(self, form):
    #     form.instance.user = self.request.user
    #     return super(CourseStudentCreate, self).form_valid(form)
#

@staff_member_required
def end_active_semester(request):
    if not request.user.is_superuser:
        return HttpResponse(status=401)

    from courses.models import Semester
    sem = Semester.objects.complete_active_semester()
    if sem is -1:
        messages.warning(request,
        "Semester is already closed, no action taken.")
    if sem is -2:
        messages.warning(request,
        "There are still quests awaiting approval. Can't close the Semester \
        until they are approved or returned")
    else:
        messages.success(request, "Semester " + str(sem) + " has been closed.")

    return redirect('config')


@login_required
def ajax_progress_chart(request, user_id=0):
    if user_id == 0:
        user = request.user
    else:
        user = get_object_or_404(User, pk=user_id)


    if request.is_ajax() and request.method == "POST":
        xp_data = []
        # generate an list of dictionary data:
        #   x: day into course
        #   y: XP earned so far

        days_so_far = 35
        import random
        xp_total = 0;
        for day in range(days_so_far):
            #xp_today = profile.user.get_xp_upto_day(day)

            # generate fake data

            xp_total += random.randint(0,1)*10
            xp_total += random.randint(0,1)*10
            xp_total += random.randint(0,1)*5

            xp_data.append(
                { 'x': day, 'y': xp_total}
            )

        print(xp_data)


        progress_chart = {
            "xp_data": xp_data,
        }
        json_data = json.dumps(progress_chart)

        return HttpResponse(json_data, content_type='application/json' )
    else:
        raise Http404
