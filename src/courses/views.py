import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import (Http404, HttpResponse, get_object_or_404,
                              redirect, render)
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView

from siteconfig.models import SiteConfig
# from .forms import ProfileForm
from tenant.views import AllowNonPublicViewMixin, allow_non_public_view

from .forms import CourseStudentForm
from .models import CourseStudent, Rank, Semester


# Create your views here.
@allow_non_public_view
@login_required
def mark_calculations(request, user_id=None):
    template_name = 'courses/mark_calculations.html'

    if not SiteConfig.get().display_marks_calculation:
        raise Http404

    # Only allow staff to see other student's mark page
    if user_id is not None and request.user.is_staff:
        user = get_object_or_404(User, pk=user_id)
    else:
        user = request.user

    course_student = CourseStudent.objects.current_course(user)
    courses = CourseStudent.objects.current_courses(user)
    num_courses = courses.count()
    if courses:
        xp_per_course = user.profile.xp_cached / num_courses
    else:
        xp_per_course = None

    context = {
        'user': user,
        'obj': course_student,
        'courses': courses,
        'xp_per_course': xp_per_course,
        'num_courses': num_courses,
    }
    return render(request, template_name, context)


class RankList(AllowNonPublicViewMixin, ListView):
    model = Rank


class CourseStudentList(AllowNonPublicViewMixin, ListView):
    model = CourseStudent


@allow_non_public_view
@staff_member_required
def add_course_student(request, user_id):
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
        return redirect('profiles:profile_detail', pk=user.profile.id)

    context = {
        "user": user,
        "form": form,
    }
    return render(request, 'courses/coursestudent_form.html', context)


class CourseStudentCreate(AllowNonPublicViewMixin, SuccessMessageMixin, CreateView):
    model = CourseStudent
    form_class = CourseStudentForm
    # fields = ['semester', 'block', 'course', 'grade']
    success_url = reverse_lazy('quests:quests')
    success_message = "You have been added to the %(course)s %(grade_fk)s course"

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

@allow_non_public_view
@staff_member_required
def end_active_semester(request):
    if not request.user.is_superuser:
        return HttpResponse(status=401)

    sem = Semester.objects.complete_active_semester()
    semester_warnings = {
        Semester.CLOSED: 'Semester is already closed, no action taken.',
        Semester.QUEST_AWAITING_APPROVAL: "There are still quests awaiting approval. Can't close the Semester \
             until they are approved or returned",
        'success': 'Semester {sem} has been closed.'.format(sem=sem),
    }

    messages.warning(
        request,
        semester_warnings.get(sem, semester_warnings['success']))

    return redirect('config')


@allow_non_public_view
@login_required
def ajax_progress_chart(request, user_id=0):
    if user_id == 0:
        user = request.user
    else:
        user = get_object_or_404(User, pk=user_id)

    if request.is_ajax() and request.method == "POST":
        sem = SiteConfig.get().active_semester

        # generate a list of dates, from first date of semester to today
        datelist = []
        for i in range(1, sem.days_so_far() + 1):
            # need to ignore weekends and non-class days
            next_day_of_class = sem.get_datetime_by_days_since_start(i, add_holidays=True)
            datelist.append(next_day_of_class)

        xp_data = []
        # generate an list of dictionary data for chart.js:
        #   x: day into course
        #   y: XP earned so far

        xp = 0
        num_courses = user.profile.num_courses()
        # days_so_far == len(datelist)
        for day in range(0, sem.days_so_far()):
            xp = user.profile.xp_to_date(datelist[day]) / num_courses
            xp_data.append(
                # day 0-indexed
                {'x': day + 1, 'y': xp}
            )

        progress_chart = {
            "days_in_semester": sem.num_days(),
            "xp_data": xp_data,
        }
        json_data = json.dumps(progress_chart)

        return HttpResponse(json_data, content_type='application/json')
    else:
        raise Http404
