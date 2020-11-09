import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import Http404, HttpResponse, get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from announcements.models import Announcement
from siteconfig.models import SiteConfig
# from .forms import ProfileForm
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .forms import BlockForm, CourseStudentForm, SemesterForm
from .models import Block, Course, CourseStudent, Rank, Semester


# Create your views here.
@non_public_only_view
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


class RankList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Rank


@method_decorator(staff_member_required, name='dispatch')
class CourseList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Course


@method_decorator(staff_member_required, name='dispatch')
class CourseCreate(NonPublicOnlyViewMixin, CreateView):
    fields = ('title', 'xp_for_100_percent', 'icon', 'active')
    model = Course
    success_url = reverse_lazy('courses:course_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = 'Create New Course'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class CourseUpdate(NonPublicOnlyViewMixin, UpdateView):
    fields = ('title', 'xp_for_100_percent', 'icon', 'active')
    model = Course
    success_url = reverse_lazy('courses:course_list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Update Course'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class CourseDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Course
    success_url = reverse_lazy('courses:course_list')


@method_decorator(staff_member_required, name='dispatch')
class CourseAddStudent(NonPublicOnlyViewMixin, CreateView):
    model = CourseStudent
    form_class = CourseStudentForm
    template_name = 'courses/coursestudent_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user = get_object_or_404(User, pk=self.kwargs.get('user_id'))
        kwargs['instance'] = CourseStudent(user=user)
        return kwargs

    def get_success_url(self):
        return reverse('profiles:profile_detail', args=(self.object.user.profile.id, ))


class CourseStudentCreate(NonPublicOnlyViewMixin, SuccessMessageMixin, LoginRequiredMixin, CreateView):
    model = CourseStudent
    form_class = CourseStudentForm
    # fields = ['semester', 'block', 'course', 'grade']
    success_url = reverse_lazy('quests:quests')
    success_message = "You have been added to the %(course)s %(grade_fk)s course"

    def get_form_kwargs(self):
        kwargs = super(CreateView, self).get_form_kwargs()
        kwargs['instance'] = CourseStudent(user=self.request.user)
        return kwargs


@method_decorator(staff_member_required, name='dispatch')
class SemesterList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Semester


@method_decorator(staff_member_required, name='dispatch')
class SemesterDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    model = Semester


@method_decorator(staff_member_required, name='dispatch')
class SemesterCreate(NonPublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Semester
    form_class = SemesterForm
    success_url = reverse_lazy('courses:semester_list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Create New Semester'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class SemesterUpdate(NonPublicOnlyViewMixin, LoginRequiredMixin, UpdateView):
    model = Semester
    form_class = SemesterForm
    success_url = reverse_lazy('courses:semester_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = 'Update Semester'
        kwargs['submit_btn_value'] = 'Update'
        kwargs['update_via_admin'] = True

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BlockList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Block


@method_decorator(staff_member_required, name='dispatch')
class BlockCreate(NonPublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Block
    form_class = BlockForm
    success_url = reverse_lazy('courses:block_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = 'Create New Block'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BlockUpdate(NonPublicOnlyViewMixin, LoginRequiredMixin, UpdateView):
    model = Block
    form_class = BlockForm
    success_url = reverse_lazy('courses:block_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = 'Update Block'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BlockDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Block
    success_url = reverse_lazy('courses:block_list')


@non_public_only_view
@staff_member_required
def end_active_semester(request):
    sem = Semester.objects.complete_active_semester()
    semester_warnings = {
        Semester.CLOSED: 'Semester is already closed, no action taken.',
        Semester.QUEST_AWAITING_APPROVAL: "There are still quests awaiting approval. Can't close the Semester \
             until they are approved or returned",
        'success': 'Semester {sem} has been closed.'.format(sem=sem),
    }

    if sem not in (Semester.CLOSED, Semester.QUEST_AWAITING_APPROVAL):
        sem.reset_students_xp_cached()

    Announcement.objects.archive_announcements()

    messages.warning(
        request,
        semester_warnings.get(sem, semester_warnings['success']))

    return redirect('config:site_config_update_own')


@non_public_only_view
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
