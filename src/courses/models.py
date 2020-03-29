from datetime import timedelta, date, datetime

import numpy
from django.conf import settings
from django.core.validators import validate_comma_separated_integer_list
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from djconfig import config
import djconfig
from jchart import Chart
from jchart.config import DataSet, rgba
from workdays import networkdays, workday
from colorful.fields import RGBColorField

from utilities.models import ImageResource

from prerequisites.models import IsAPrereqMixin
from quest_manager.models import QuestSubmission


class MarkRangeManager(models.Manager):
    def get_range(self, mark, courses=None):
        """ return the MarkRange encompassed by this mark adn the list of courses """
        self.get_queryset().filter(active=True)
        day = timezone.localtime(timezone.now()).isoweekday()
        # ranges for all courses
        ranges_qs = self.get_queryset().filter(active=True, courses=None, days__contains=str(day))
        if courses:
            for course in courses:
                courses_qs = course.markrange_set.filter(active=True, days__contains=str(day))  # ranges for this course
                ranges_qs = ranges_qs | courses_qs

        ranges_qs = ranges_qs.filter(minimum_mark__lte=mark)  # filter out ranges that are too high

        return ranges_qs.last()  # return the highest range that qualifies

    def get_range_for_user(self, user):
        mark = user.profile.mark()
        student_course_ids = user.profile.current_courses().values_list('course', flat=True)
        if student_course_ids:
            courses = Course.objects.filter(id__in=student_course_ids)
            return self.get_range(mark, courses)
        else:
            return None


class MarkRange(models.Model):
    name = models.CharField(max_length=50, default="Chillax Line")
    minimum_mark = models.FloatField(default=72.5, help_text="Minimum mark as a percentage from 0 to 100 (or higher)")
    active = models.BooleanField(default=True)
    color_light = RGBColorField(default='#BEFFFA', help_text='Color to be used in the light theme')
    color_dark = RGBColorField(default='#337AB7', help_text='Color to be used in the dark theme')
    days = models.CharField(
        validators=[validate_comma_separated_integer_list],
        max_length=13,
        help_text='Comma seperated list of weekdays that this range is active, where Monday=1 and Sunday=7. \
                   E.g.: "1,3,5" for M, W, F.',
        default="1,2,3,4,5,6,7"
    )
    courses = models.ManyToManyField(
        "courses.course",
        blank=True,
        help_text="Which courses this field is relevant to; If left blank it will apply to all courses."
    )

    objects = MarkRangeManager()

    class Meta:
        ordering = ['minimum_mark']

    def __str__(self):
        return self.name + " (" + str(self.minimum_mark) + "%)"


class RankQuerySet(models.query.QuerySet):
    def get_ranks_lte(self, xp):
        return self.filter(xp__lte=xp)

    def get_ranks_gt(self, xp):
        return self.filter(xp__gt=xp)


class RankManager(models.Manager):
    def get_queryset(self):
        return RankQuerySet(self.model, using=self._db).order_by('xp')

    def get_rank(self, user_xp=0):
        if user_xp < 0:
            user_xp = 0
        return self.get_queryset().get_ranks_lte(user_xp).last()

    def get_next_rank(self, user_xp=0):
        return self.get_queryset().get_ranks_gt(user_xp).first()


class Rank(models.Model, IsAPrereqMixin):
    name = models.CharField(max_length=50, unique=False, null=True)
    xp = models.PositiveIntegerField(help_text='The XP at which this rank is granted')
    icon = models.ImageField(upload_to='icons/ranks/', null=True, blank=True,
                             help_text="A backup where fa_icon can't be used.  E.g. in the quest maps.")
    fa_icon = models.TextField(null=True, blank=True,
                               help_text='html to render a font-awesome icon or icon stack etc.')

    objects = RankManager()

    class Meta:
        ordering = ['xp']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('courses:ranks')

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url

        if config.hs_default_icon:
            icon = get_object_or_404(ImageResource, pk=config.hs_default_icon)
            return icon.image.url
        return static('img/default_icon.png')

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        # profile = Profile.objects.get(user=user)
        return user.profile.xp_cached >= self.xp

    def get_map(self):
        from djcytoscape.models import CytoScape
        return CytoScape.objects.get_map_for_init(self)


class Grade(models.Model, IsAPrereqMixin):
    name = models.CharField(max_length=20, unique=True)
    value = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return str(self.name)

    class Meta:
        ordering = ["value"]

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        coursestudents = CourseStudent.objects.current_courses(user)
        if coursestudents.filter(grade_fk__value=self.value):
            return True
        else:
            return False


class SemesterManager(models.Manager):
    def get_queryset(self):
        return models.query.QuerySet(self.model, using=self._db).order_by('-first_day')

    def get_current(self, as_queryset=False):
        if as_queryset:
            return self.get_queryset().filter(pk=config.hs_active_semester)
        else:
            return self.get_queryset().get(pk=config.hs_active_semester)

    def set_active(self, active_sem_id):
        sems = self.get_queryset()
        for sem in sems:
            if sem.id == active_sem_id:
                sem.active = True
            else:
                sem.active = False
            sem.save()

    def complete_active_semester(self):

        active_sem = self.get_current()

        # This semester has already been closed
        if active_sem.closed:
            return -1

        # There are still quests awaiting approval, can't close!
        if QuestSubmission.objects.all_awaiting_approval():
            return -2

        # need to calculate all user XP and store in their Course
        CourseStudent.objects.calc_semester_grades(active_sem)

        QuestSubmission.objects.remove_in_progress()

        active_sem.closed = True
        active_sem.save()

        return active_sem


def default_end_date():
    return date.today() + timedelta(days=135)


class Semester(models.Model):
    SEMESTER_CHOICES = ((1, 1), (2, 2),)

    number = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
    first_day = models.DateField(blank=True, null=True, default=date.today)
    last_day = models.DateField(blank=True, null=True, default=default_end_date)
    active = models.BooleanField(default=False)
    closed = models.BooleanField(
        default=False,
        help_text="All student courses in this semester have been closed and final marks recorded."
    )

    objects = SemesterManager()

    class Meta:
        get_latest_by = "first_day"
        ordering = ['first_day']

    def __str__(self):
        return self.first_day.strftime("%b-%Y")

    def active_by_date(self):
        # use local date `datetime.date.today()` instead of UTC date from `timezone.now().date()`
        return (self.last_day + timedelta(days=5)) > date.today() > (self.first_day - timedelta(days=20))

    def is_open(self):
        """
        :return: True if the current date falls within the semeseter's first and last day (inclusive)
        """
        # don't use timezone.now().date() because it uses UTC, and might not be the same as
        # the current local date.  Use current local date with date.today()
        return self.first_day <= date.today() <= self.last_day

    def num_days(self, upto_today=False):
        '''The number of classes in the semester (from start date to end date
        excluding weekends and ExcludedDates) '''

        excluded_days = self.excluded_days()
        if upto_today and date.today() < self.last_day:
            last_day = date.today()
        else:
            last_day = self.last_day
        return networkdays(self.first_day, last_day, excluded_days)

    def excluded_days(self):
        return self.excludeddate_set.all().values_list('date', flat=True)

    def days_so_far(self):
        return self.num_days(True)

    def fraction_complete(self):
        current_days = self.num_days(True)
        total_days = self.num_days()
        return current_days / total_days

    def percent_complete(self):
        return self.fraction_complete() * 100.0

    def get_interim1_date(self):
        return self.get_date(0.25)

    def get_term_date(self):
        return self.get_date(0.5)

    def get_interim2_date(self):
        return self.get_date(0.75)

    def get_final_date(self):
        return self.last_day

    def get_date(self, fraction_complete):
        days = self.num_days()
        days_to_fraction = int(days * fraction_complete)
        excluded_days = self.excluded_days()
        return workday(self.first_day, days_to_fraction, excluded_days)

    def get_datetime_by_days_since_start(self, class_days, add_holidays=False):
        excluded_days = self.excluded_days()

        # The next day of class excluding holidays/weekends
        date = workday(self.first_day, class_days, excluded_days)

        # Might want to include the holidays (if class day is Friday, then work done on weekend/holidays won't show up
        # till Monday.  For chart, want to include those days
        if (add_holidays):
            next_date = workday(self.first_day, class_days + 1, excluded_days)
            num_holidays_to_add = next_date - date - timedelta(days=1)  # If more than one day difference
            date += num_holidays_to_add

        # convert from date to datetime
        dt = datetime.combine(date, datetime.max.time())
        # make timezone aware
        return timezone.make_aware(dt, timezone.get_default_timezone())

    # def chillax_line_started(self):
    #     # return timezone.now().date() > self.get_interim1_date()
    #     return config.hs_chillax_line_active

    # def chillax_line(self):
    #     cline = config.hs_chillax_line
    #     fraction = self.fraction_complete()
    #     return round(1000 * cline * fraction)

    def get_student_mark_list(self, students_only=False):
        students = CourseStudent.objects.all_users_for_active_semester(students_only=students_only)
        mark_list = []
        for student in students:
            mark_list.append(student.profile.mark())
        return mark_list


class DateType(models.Model):
    date_type = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.date_type


class Block(models.Model):
    block = models.CharField(max_length=50, unique=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    current_teacher = models.ForeignKey(settings.AUTH_USER_MODEL,
                                        null=True, blank=True,
                                        limit_choices_to={'is_staff': True},
                                        on_delete=models.SET_NULL)

    def __str__(self):
        return self.block

    class Meta:
        ordering = ["start_time"]


class ExcludedDate(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    date_type = models.ForeignKey(DateType, on_delete=models.SET_NULL, null=True)
    date = models.DateField(unique=True)

    def __str__(self):
        return self.date.strftime("%d-%b-%Y")


class Course(models.Model, ):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    xp_for_100_percent = models.PositiveIntegerField(default=1000)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["title"]

    # # required for prereq mixin (grapelli lookup) since no name field already.
    # @property
    # def name(self):
    #     return self.title

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        coursestudents = CourseStudent.objects.current_courses(user)
        if coursestudents.filter(course__pk=self.pk):
            return True
        else:
            return False

    @staticmethod
    def autocomplete_search_fields():  # for grapelli prereq selection
        return ("title__icontains",)


class CourseStudentQuerySet(models.query.QuerySet):
    def sticky(self):
        return self.filter(sticky=True)

    def get_user(self, user):
        return self.filter(user=user)

    def get_semester(self, semester):
        return self.filter(semester=semester)

    def get_not_semester(self, semester):
        return self.exclude(semester=semester)

    def get_active(self):
        return self.filter(active=True)

    def get_inactive(self):
        return self.filter(active=False)

    def get_students_only(self):
        return self.filter(user__is_staff=False, user__profile__is_test_account=False)


class CourseStudentManager(models.Manager):
    def get_queryset(self):
        return CourseStudentQuerySet(self.model, using=self._db)

    def all_for_user_semester(self, user, semester):
        return self.get_queryset().get_user(user).get_semester(semester)

    def all_for_user_not_semester(self, user, semester):
        return self.get_queryset().get_user(user).get_not_semester(semester)

    def all_for_user(self, user):
        return self.get_queryset().get_user(user)

    def all_for_user_active(self, user, active):
        if active:
            return self.all_for_user(user).get_active()
        else:
            return self.all_for_user(user).get_inactive()

    # for current active semester
    def calculate_xp(self, user):
        xp = 0
        studentcourses = self.current_courses(user)
        if studentcourses:
            for studentcourse in studentcourses:
                xp += studentcourse.xp_adjustment
        return xp

    def calc_semester_grades(self, semester):
        coursestudents = self.get_queryset().get_semester(semester)
        for coursestudent in coursestudents:
            coursestudent.final_xp = coursestudent.user.profile.xp_per_course()
            coursestudent.active = False
            coursestudent.save()

    def all_for_semester(self, semester, students_only=False):
        qs = self.get_queryset().get_semester(semester)
        if students_only:
            qs = qs.get_students_only()
        return qs

    # pick one of the courses...for now
    def current_course(self, user):
        return self.current_courses(user).first()

    def current_courses(self, user):
        djconfig.reload_maybe()  # prevent celery tasks from breaking when run manually
        return self.all_for_user(user).get_semester(config.hs_active_semester)

    def all_users_for_active_semester(self, students_only=False):
        """
        :return: queryset of all Users who are enrolled in a course during the active semester (doubles removed)
        """
        courses = self.all_for_semester(config.hs_active_semester, students_only=students_only)
        user_list = courses.values_list('user', flat=True)
        user_list = set(user_list)  # removes doubles
        return User.objects.filter(id__in=user_list)

    # @cached(60*60*12)
    def get_current_teacher_list(self, user):
        return self.current_courses(user).values_list('block__current_teacher', flat=True)


class CourseStudent(models.Model):
    GRADE_CHOICES = ((9, 9), (10, 10), (11, 11), (12, 12), (13, 'Adult'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.SET_NULL, null=True)
    block = models.ForeignKey(Block, on_delete=models.SET_NULL, null=True)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True)
    # grade = models.PositiveIntegerField(choices=GRADE_CHOICES, null=True, blank=True)
    grade_fk = models.ForeignKey(Grade, verbose_name="Grade", on_delete=models.SET_NULL, null=True)
    xp_adjustment = models.IntegerField(default=0)
    xp_adjust_explanation = models.CharField(max_length=255, blank=True, null=True)
    final_xp = models.PositiveIntegerField(blank=True, null=True)
    final_grade = models.PositiveIntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)

    objects = CourseStudentManager()

    class Meta:
        unique_together = (
            ('semester', 'block', 'user'),
            ('user', 'course', 'grade_fk'),
        )
        verbose_name = "Student Course"
        ordering = ['-semester', 'block']

    def __str__(self):
        return self.user.get_username() \
            + ", " + str(self.semester) if self.semester else "" \
            + ", " + str(self.block.block) if self.block else "" \
            + ": " + str(self.course) \
            + " " + str(self.grade_fk.value) if self.grade_fk else ""

    def get_absolute_url(self):
        return reverse('courses:list')
        # return reverse('courses:detail', kwargs={'pk': self.pk})

    # @cached_property
    def calc_mark(self, xp):
        fraction_complete = self.semester.fraction_complete()
        if fraction_complete > 0:
            return xp / fraction_complete * 100 / self.course.xp_for_100_percent
        else:
            return 0

    def xp_per_day_ave(self):
        days = self.semester.days_so_far()
        if days > 0:
            return self.user.profile.xp_cached / self.semester.days_so_far()
        else:
            return 0


@receiver(post_save, sender=CourseStudent)
def coursestudent_post_save_callback(instance, **kwargs):
    """
    This model's objects are edited by teachers using the admin menu.
    If they make a manual XP adjustment we need to invalidate the user's xp_cache to recalculate xp
    """
    instance.user.profile.xp_invalidate_cache()


class MarkDistributionHistogram(Chart):
    chart_type = 'bar'
    scales = {
        'xAxes': [{
            'barPercentage': 1.05,
            'categoryPercentage': 1.05,
            'gridLines': {
                'offsetGridLines': False,
                'display': False,
            },
            'stacked': True,
            # 'scaleLabel': {
            #   'display': True,
            #   'labelString': 'Current mark as a percentage'
            # }
        }],
        'yAxes': [{
            'stacked': True,
            # 'scaleLabel': {
            #     'display': True,
            #     'labelString': '# of students in this mark range'
            # }
        }]

    }
    options = {
        'maintainAspectRatio': False,
    }
    histogram = {'labels': [], 'data': []}
    bin_size = 10

    def get_labels(self, **kwargs):

        if not self.histogram['labels']:
            self.generate_histogram()
        return self.histogram['labels']

    def get_datasets(self, user_id):

        if not self.histogram['data']:
            self.generate_histogram()

        user_data = self.generate_user_data(user_id)  # needs to be before getting histogram data
        all_course_data = self.histogram['data']

        course_dataset = DataSet(label='# of other students in this mark range',
                                 data=all_course_data,
                                 borderWidth=1,
                                 backgroundColor=rgba(128, 128, 128, 0.3),
                                 borderColor=rgba(0, 0, 0, 0.2),
                                 )
        # course_dataset['stack'] = 'marks'

        user_dataset = DataSet(label='You',
                               data=user_data,
                               )
        # user_dataset['stack'] = 'marks'

        return [course_dataset, user_dataset, ]

    def generate_user_data(self, user_id):
        """ Create a list for the histogram filled with 0's except the bin with the user's mark
        """
        user = User.objects.get(id=user_id)
        user_mark = user.profile.mark()
        data = []
        index = 0
        for mark_bin in range(0, 100 + self.bin_size, self.bin_size):
            if mark_bin <= user_mark < mark_bin + self.bin_size:
                data.append(1)
                # Remove this data point from the main data
                self.histogram['data'][index] -= 1
            else:
                data.append(0)
            index += 1
        return data

    def generate_histogram(self):
        data = Semester.objects.get_current().get_student_mark_list(students_only=True)
        # data = numpy.random.normal(0, 20, 1000)
        right_edge = 100 + self.bin_size
        bins = numpy.arange(0, right_edge, self.bin_size)
        bins_list = bins.tolist()  # numpy uses some weird ass array format, lets get a list from it
        bins_list.append(999)  # include everything >100 in the last bin
        hist, bin_edges = numpy.histogram(data, bins_list)
        self.histogram['data'] = hist.tolist()

        # do some work to get labels correct
        # don't wan't the last bin 999 to appear as a label on the chart
        bin_labels = [str(bin_label) + "%" for bin_label in bins_list]
        bin_labels[-1] = ""
        bin_labels[-2] = "100%+"
        self.histogram['labels'] = bin_labels
