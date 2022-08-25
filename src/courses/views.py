import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import Http404, HttpResponse, get_object_or_404, redirect, render, reverse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from hackerspace_online.decorators import staff_member_required

from announcements.models import Announcement
from siteconfig.models import SiteConfig
from tags.models import get_user_tags_and_xp, get_quest_submission_by_tag, get_badge_assertion_by_tags
# from .forms import ProfileForm
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .forms import BlockForm, CourseStudentForm, CourseStudentStaffForm, SemesterForm, ExcludedDateFormset, ExcludedDateFormsetHelper
from .models import Block, Course, CourseStudent, Rank, Semester, MarkRange
from quest_manager.models import Quest
from badges.models import Badge

import numpy


# Create your views here.
@non_public_only_view
@login_required
def mark_calculations(request, user_id=None):
    template_name = 'courses/mark_calculations.html'

    # Mark calculation not activated on this deck
    if not SiteConfig.get().display_marks_calculation:
        if request.user.is_staff:
            template_name = "courses/mark_calculations_deactivated.html"
            return render(request, template_name)
        else:
            # Students should be here, they must have entered URL manually
            raise Http404()

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

    # only show mark ranges where student is enrolled in and is also active
    user_courses = user.profile.current_courses().values_list('course', flat=True)
    assigned_ranges = MarkRange.objects.filter(active=True, courses__in=user_courses)
    all_ranges = MarkRange.objects.filter(active=True, courses=None) 

    # combine assigned_ranges and all_ranges, then order by min mark
    markranges = (assigned_ranges | all_ranges).order_by('minimum_mark')

    context = {
        'user': user,
        'obj': course_student,
        'courses': courses,
        'xp_per_course': xp_per_course,
        'num_courses': num_courses,
        'markranges': markranges,
    }
    return render(request, template_name, context)


class RankList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Rank


@method_decorator(staff_member_required, name='dispatch')
class RankCreate(NonPublicOnlyViewMixin, CreateView):
    fields = ('name', 'xp', 'icon', 'fa_icon')
    model = Rank
    success_url = reverse_lazy('courses:ranks')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = 'Create New Rank'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class RankUpdate(NonPublicOnlyViewMixin, UpdateView):
    fields = ('name', 'xp', 'icon', 'fa_icon')
    model = Rank
    success_url = reverse_lazy('courses:ranks')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Update Rank'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class RankDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Rank
    success_url = reverse_lazy('courses:ranks')


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = self.get_object()

        course_student_qs = self.get_object().coursestudent_set
        context["population"] = course_student_qs.count()
        context["populated"] = course_student_qs.exists()
        return context


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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['heading'] = 'Add student to course'
        ctx['submit_btn_value'] = 'Add'
        return ctx

    def get_success_url(self):
        return reverse('profiles:profile_detail', args=(self.object.user.profile.id, ))


@method_decorator(staff_member_required, name='dispatch')
class CourseStudentUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = CourseStudent
    form_class = CourseStudentStaffForm
    template_name = 'courses/coursestudent_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['heading'] = f'Update {self.object.user.username}\'s course'
        ctx['submit_btn_value'] = 'Update'
        return ctx

    def get_success_url(self):
        return reverse('profiles:profile_detail', args=[self.object.user.profile.id])


class CourseStudentCreate(NonPublicOnlyViewMixin, SuccessMessageMixin, LoginRequiredMixin, CreateView):
    model = CourseStudent
    form_class = CourseStudentForm
    # fields = ['semester', 'block', 'course', 'grade']
    success_url = reverse_lazy('quests:quests')
    success_message = "You have been added to the %(course)s course"

    def get_form_kwargs(self):
        kwargs = super(CreateView, self).get_form_kwargs()
        kwargs['instance'] = CourseStudent(user=self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['heading'] = 'Join a course'
        ctx['submit_btn_value'] = 'Join'
        return ctx


@method_decorator(staff_member_required, name='dispatch')
class SemesterList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Semester


@method_decorator(staff_member_required, name='dispatch')
class SemesterDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    model = Semester


class SemesterCreateUpdateFormsetMixin:
    formset_class = ExcludedDateFormset

    def get(self, *args, **kwargs):
        self.object = self.get_object()
        return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self.object = self.get_object()
        forms = [self.get_form(), self.get_formset()]

        if all([form.is_valid() for form in forms]):
            return self.form_valid(*forms)
        return self.form_invalid(*forms)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs).copy()
        ctx['formset'] = kwargs.get('formset', self.get_formset())
        ctx['helper'] = ExcludedDateFormsetHelper()
        return ctx

    # formsets 

    def get_formset_queryset(self):
        return self.get_object().excludeddate_set.all().order_by('date')

    def get_formset_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        # wrong instance, therefore get rid of it
        form_kwargs.pop('instance')  # instance will be passed as a kwarg automatically by formset anyway

        form_kwargs['form_kwargs'] = {
            'semester': self.object,
        }
        return form_kwargs
        
    def get_formset(self):
        return self.formset_class(**self.get_formset_kwargs(), queryset=self.get_formset_queryset())
    
    # form

    def form_valid(self, form, formset):
        response = super().form_valid(form)  # has to be before formset.save() so CreateView can save model first (necessary for create view)
        formset.save()
        return response

    def form_invalid(self, form, formset):
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


@method_decorator(staff_member_required, name='dispatch')
class SemesterCreate(SemesterCreateUpdateFormsetMixin, NonPublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Semester
    form_class = SemesterForm
    success_url = reverse_lazy('courses:semester_list')

    def get_object(self):
        return self.model()

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Create New Semester'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class SemesterUpdate(SemesterCreateUpdateFormsetMixin, NonPublicOnlyViewMixin, LoginRequiredMixin, UpdateView):
    model = Semester
    form_class = SemesterForm
    success_url = reverse_lazy('courses:semester_list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Update Semester'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class SemesterActivate(View):

    def get(self, request, *args, **kwargs):
        semester_pk = self.kwargs['pk']
        semester = get_object_or_404(Semester, pk=semester_pk)
        siteconfig = SiteConfig.objects.get()
        siteconfig.active_semester = semester
        siteconfig.save()

        return redirect('courses:semester_list')


@method_decorator(staff_member_required, name='dispatch')
class BlockList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Block


@method_decorator(staff_member_required, name='dispatch')
class BlockCreate(NonPublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Block
    form_class = BlockForm
    success_url = reverse_lazy('courses:block_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = f'Create New {SiteConfig.objects.get().custom_name_for_group}'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BlockUpdate(NonPublicOnlyViewMixin, LoginRequiredMixin, UpdateView):
    model = Block
    form_class = BlockForm
    success_url = reverse_lazy('courses:block_list')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = f'Update {SiteConfig.objects.get().custom_name_for_group}'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BlockDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Block
    success_url = reverse_lazy('courses:block_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        course_student_qs = self.get_object().coursestudent_set
        context['population'] = course_student_qs.count()
        context['populated'] = course_student_qs.exists()
        return context


@non_public_only_view
@staff_member_required
def end_active_semester(request):
    sem = Semester.objects.complete_active_semester()
    semester_warnings = {
        Semester.CLOSED: 'Semester is already closed, no action taken.',
        Semester.QUEST_AWAITING_APPROVAL: "There are still quests awaiting approval. Can't close the Semester until they are approved or returned",
        'success': f'Semester {sem} has been closed: student XP has been recorded and reset to 0, in-progress quests have been deleted, and \
        announcements have been archived.',
    }

    if sem not in (Semester.CLOSED, Semester.QUEST_AWAITING_APPROVAL):
        sem.reset_students_xp_cached()
        Announcement.objects.archive_announcements()

    messages.warning(
        request,
        semester_warnings.get(sem, semester_warnings['success']))

    return redirect('courses:semester_list')


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


class Ajax_MarkDistributionChart(NonPublicOnlyViewMixin, View):
    _BINS = 10
    _BIN_WIDTH = 10

    def dispatch(self, request, *args, **kwargs):
        is_ajax = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
        if not is_ajax or not request.user.is_authenticated:
            raise Http404() 

        return super().dispatch(request, *args, **kwargs)

    def get(self, *args, **kwargs):
        self.user = self.get_user()
        json_data = self.get_json_data()

        return HttpResponse(json_data, content_type='application/json')

    def get_user(self):
        pk = self.kwargs['user_id']
        return get_object_or_404(User, pk=pk)

    def get_datasets(self):
        """query datasets for both histograms ( marks over 100% will be capped at 100% )

        Returns:
            tuple[int, list[ints]]: queried user's mark and all students in active semester's mark
        """
        # grab dataset
        user_mark = self.user.profile.mark() or 0  # can be nonetype
        student_marks = Semester.get_student_mark_list(Semester, students_only=True)
        # only remove user's mark from student_marks if user is part of active sem
        if CourseStudent.objects.all_users_for_active_semester(students_only=True).filter(id=self.user.id).exists():
            student_marks.remove(user_mark)

        # limit marks, so marks > 100 can show on histogram
        user_mark = min(user_mark, 100)
        student_marks = numpy.clip(student_marks, 0, 100)

        return user_mark, student_marks

    def generate_histograms(self):
        """generates histograms

        Returns:
            tuple[list[int], list[int], list[int]]: 

                for first two list in tuple:
                    histogram of values using student and queried user's marks 

                last el in tuple:
                    histogram's bins in list form
        """
        user_mark, student_marks = self.get_datasets()

        # histogram length will be len(bin)-1, so bin length has to be self._BIN_SIZE+1
        bins = numpy.arange(0, self._BINS * (self._BIN_WIDTH + 1) + 1, self._BIN_WIDTH)  
        student_histogram, _ = numpy.histogram(student_marks, bins=bins)
        user_histogram, _ = numpy.histogram(user_mark, bins=bins)

        return student_histogram, user_histogram, bins

    def get_json_data(self):
        student_histogram, user_histogram, bins = self.generate_histograms()

        # combine histogram
        student_histogram = numpy.add(student_histogram, user_histogram)
        # make histogram json serializable (int64 -> int)
        student_histogram = list(map(int, student_histogram))

        # this will tell use where in the student_histogram user data point was added
        user_histogram = list(user_histogram)
        user_id = user_histogram.index(max(user_histogram))

        # labels
        # 0%, 10%, 20%, ... , 100%+
        bin_labels = [str(bin_) + "%" for bin_ in bins[:len(bins) - 1]]
        bin_labels[-1] += "+"
        # last dataset (index 11) will be hidden with maintainAspectRatio=False
        # add empty label so it can show
        bin_labels.append("")

        return json.dumps({
            'labels': bin_labels,  # list[str]
            'data': {
                'user_id': user_id,  # int
                'students': student_histogram,  # list[int]
            }
        })


class Ajax_TagChart(NonPublicOnlyViewMixin, View):

    def dispatch(self, request, *args, **kwargs):
        is_ajax = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
        if not is_ajax or not request.user.is_authenticated:
            raise Http404()

        return super().dispatch(request, *args, **kwargs)

    def get(self, *args, **kwargs):
        self.user = self.get_user()
        json_data = self.get_json_data()

        return HttpResponse(json_data, content_type='application/json')

    def get_user(self):
        pk = self.kwargs['user_id']
        return get_object_or_404(User, pk=pk)

    def get_quest_dataset(self, user_tags):
        """  Quest dataset for chart.js to use to display bar chart for quest objects

        Args:
            user_tags (str, QS[Tag]): all tags related to user

        Returns:
            list[dict[str, list[int]]]: returns dictionary of str, list[int]
                el 0 -> str: name of quest object so we can use that as helptext label
                el 1 -> list[int]: 
                    list has 2 values, 0 or xp. list[index] == 0 means that quest doesn't have tag for user_tags[index].
                    If list[index] == quest.xp then quest has tag user_tags[index]
        """
        quest_ids = list(get_quest_submission_by_tag(self.user, user_tags).values_list('quest__id', flat=True))
        quest_queryset = Quest.objects.filter(id__in=quest_ids)  # all quests related to user

        quest_dataset = []
        for quest in quest_queryset:
            quest_tags = quest.tags.all().values_list('name', flat=True)
            xp_in_tag = [quest.xp if tag in quest_tags else 0 for tag in user_tags]

            quest_dataset.append({'name': quest.name, 'dataset': xp_in_tag})
            
        return quest_dataset

    def get_badge_dataset(self, user_tags):
        """  Badge dataset for chart.js to use to display bar chart for badge objects

        Args:
            user_tags (str, QS[Tag]): all tags related to user

        Returns:
            list[dict[str, list[int]]]: returns dictionary of str, list[int]
                el 0 -> str: name of badge object so we can use that as helptext label
                el 1 -> list[int]: 
                    list has 2 values, 0 or xp. list[index] == 0 means that badge doesn't have tag for user_tags[index].
                    If list[index] == badge.xp then badge has tag user_tags[index]
        """
        badge_ids = list(get_badge_assertion_by_tags(self.user, user_tags).values_list('badge__id', flat=True))
        badge_queryset = Badge.objects.filter(id__in=badge_ids)  # all badges related to user

        badge_dataset = []
        for badge in badge_queryset:
            badge_tags = badge.tags.all().values_list('name', flat=True)
            xp_in_tag = [badge.xp if tag in badge_tags else 0 for tag in user_tags]

            badge_dataset.append({'name': badge.name, 'dataset': xp_in_tag})
            
        return badge_dataset

    def get_json_data(self):
        # get names from get_user_tags_and_xp to get it in order by tag xp
        _tag_and_xp = get_user_tags_and_xp(self.user) or [('', '')]  # use 'or' so zip has a return value
        names, _ = zip(*_tag_and_xp)
        names = list(map(str, names))  

        quest_dataset = self.get_quest_dataset(names)
        badge_dataset = self.get_badge_dataset(names)
        
        return json.dumps({
            'labels': names,  # list[str]
            'data': {
                'quest_dataset': quest_dataset,  # list[dict[str, list[int]]]
                'badge_dataset': badge_dataset,  # list[dict[str, list[int]]]
            }
        })
