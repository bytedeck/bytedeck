from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import validate_comma_separated_integer_list
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

import numpy
from colorful.fields import RGBColorField

from prerequisites.models import IsAPrereqMixin
from quest_manager.models import QuestSubmission
from siteconfig.models import SiteConfig


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
        """Return the next closest Rank with an XP value <= user_xp
        Only allow user_xp values >= 0.  If no Rank is found, then create a Rank at xp=0
        """
        if user_xp < 0:
            user_xp = 0

        rank = self.get_queryset().get_ranks_lte(user_xp).last()
        if not rank:
            rank = self.create_zero_rank()
        return rank

    def get_next_rank(self, user_xp=0):
        """Return the next closest Rank with an XP value > user_xp"""
        return self.get_queryset().get_ranks_gt(user_xp).first()

    def create_zero_rank(self):
        zero_rank = Rank(xp=0, name="None", icon="fa fa-circle-o")
        zero_rank.save()
        return zero_rank


class Rank(IsAPrereqMixin, models.Model):
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
        else:
            return SiteConfig.get().get_default_icon_url()

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        # profile = Profile.objects.get(user=user)
        return user.profile.xp_cached >= self.xp

    def get_map(self):
        from djcytoscape.models import CytoScape
        return CytoScape.objects.get_map_for_init(self)


class Grade(IsAPrereqMixin, models.Model):
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
            return self.get_queryset().filter(pk=SiteConfig.get().active_semester.pk)
        else:
            return SiteConfig.get().active_semester

    def complete_active_semester(self):

        active_sem = self.get_current()

        # This semester has already been closed
        if active_sem.closed:
            return Semester.CLOSED

        # There are still quests awaiting approval, can't close!
        if QuestSubmission.objects.all_awaiting_approval():
            return Semester.QUEST_AWAITING_APPROVAL

        # need to calculate all user XP and store in their Course
        try:
            CourseStudent.objects.calc_semester_grades(active_sem)
        except ValueError:
            return Semester.STUDENTS_WITH_NEGATIVE_XP

        QuestSubmission.objects.remove_in_progress()

        active_sem.closed = True
        active_sem.save()

        return active_sem


def default_end_date():
    return date.today() + timedelta(days=135)


class Semester(models.Model):
    CLOSED = -1
    QUEST_AWAITING_APPROVAL = -2
    STUDENTS_WITH_NEGATIVE_XP = -3

    first_day = models.DateField(null=True, default=date.today)
    last_day = models.DateField(null=True, default=default_end_date)
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
        excluding weekends and ExcludedDates). '''

        excluded_days = self.excluded_days()
        if upto_today and date.today() < self.last_day:
            last_day = date.today()
        else:
            last_day = self.last_day
        count = numpy.busday_count(self.first_day, last_day, holidays=excluded_days)
        if numpy.is_busday(last_day, holidays=excluded_days):  # end date is not included, so add here.
            count += 1
        # We want to return an int because a numpty.int64 is not JSON serializable as of the moment
        return count.item() if hasattr(count, 'item') else count

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
        """ Gets the closest date, rolling back if it falls on a weekend or excluded
        after a fraction of the semester is over """
        days = self.num_days()
        days_to_fraction = int(days * fraction_complete)
        excluded_days = self.excluded_days()
        date_after_fraction = numpy.busday_offset(self.first_day, offsets=days_to_fraction, roll='backward',
                                                  holidays=excluded_days)
        return date_after_fraction.item()

    def get_datetime_by_days_since_start(self, class_days, add_holidays=False):
        """ The date `class days` from the start of the semester

        Arguments:
            class_days {int} -- number of days since start

        Keyword Arguments:
            add_holidays {bool} -- [description] (default: {False})

        Returns:
            {datetime} -- [description]
        """
        excluded_days = self.excluded_days()

        # The next day of class excluding holidays/weekends, -1 because first day counts as 1, not zero.
        d = numpy.busday_offset(self.first_day, class_days - 1, roll='forward', holidays=excluded_days).astype(date)

        # Might want to include the holidays (if class day is Friday, then work done on weekend/holidays won't show up
        # till Monday.  For chart, want to include those days
        # if (add_holidays):
        #     next_date = numpy.busday_offset(self.first_day, class_days + 1, roll='backward', holidays=excluded_days)
        #     # next_date = workday(self.first_day, class_days + 1, excluded_days)
        #     num_holidays_to_add = next_date - d - timedelta(days=1)  # If more than one day difference
        #     d += num_holidays_to_add

        # convert from date to datetime
        dt = datetime.combine(d, datetime.max.time())
        # make timezone aware
        return timezone.make_aware(dt, timezone.get_default_timezone())

    def reset_students_xp_cached(self):

        from profile_manager.models import Profile
        profile_ids = CourseStudent.objects.all_users_for_active_semester(students_only=True).values_list('profile',
                                                                                                          flat=True)
        profile_ids = set(profile_ids)
        profiles = Profile.objects.filter(id__in=profile_ids)

        for profile in profiles:
            profile.xp_cached = 0

        Profile.objects.bulk_update(profiles, ['xp_cached'])

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


class BlockManager(models.Manager):

    def grouped_teachers_blocks(self):
        blocks = self.get_queryset().select_related('current_teacher').values_list('current_teacher', 'name')
        grouped = {}

        # Group by {teacher : [ blocks ]}
        for block in blocks:
            teacher, blk = block
            grouped.setdefault(teacher, []).append(blk)

        return grouped


class Block(IsAPrereqMixin, models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    current_teacher = models.ForeignKey(settings.AUTH_USER_MODEL,
                                        null=True, blank=True,
                                        limit_choices_to={'is_staff': True},
                                        on_delete=models.SET_NULL)
    active = models.BooleanField(default=True)

    objects = BlockManager()

    class Meta:
        ordering = ['name']
        verbose_name = 'Group'

    def __str__(self):
        return self.name

    def condition_met_as_prerequisite(self, user, num_required=1):
        """ Returns True if the user has a current course in this block/group.  `num_required` is not used.
        """
        # num_required is not used for this one
        return CourseStudent.objects.current_courses(user).filter(block=self).exists()


class ExcludedDate(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    date_type = models.ForeignKey(DateType, on_delete=models.SET_NULL, blank=True, null=True)
    date = models.DateField(unique=True)
    label = models.CharField(max_length=100, blank=True, null=True, help_text="An optional label for this date.")

    def __str__(self):
        return self.date.strftime("%d-%b-%Y")


class Course(IsAPrereqMixin, models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    xp_for_100_percent = models.PositiveIntegerField(default=1000)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('courses:course_list')

    class Meta:
        ordering = ["title"]

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
        return CourseStudentQuerySet(self.model, using=self._db).select_related('course')

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
            if coursestudent.final_xp < 0:
                raise ValueError(f"{coursestudent.user.get_full_name()} has a negative XP. "
                                 f"Fix it before closing the semester")
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
        return self.all_for_user(user).get_semester(SiteConfig.get().active_semester)

    def all_users_for_active_semester(self, students_only=False):
        """
        :return: queryset of all Users who are enrolled in a course during the active semester (doubles removed)
        """
        try:
            courses = self.all_for_semester(SiteConfig.get().active_semester, students_only=students_only)
            user_list = courses.values_list('user', flat=True)
            user_list = set(user_list)  # removes doubles
            return User.objects.filter(id__in=user_list)
        except AttributeError:
            # The code will run on the public tenant when booting up, throwing an exception because
            # the public tenant doesn't have a SiteConfig object.
            return User.objects.none()

    # @cached(60*60*12)
    def get_current_teacher_list(self, user):
        return self.current_courses(user).values_list('block__current_teacher', flat=True)


class CourseStudent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.SET_NULL, null=True)
    block = models.ForeignKey(Block, on_delete=models.PROTECT, null=True, verbose_name="Group")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, null=True)
    # grade is deprecated, shouldn't be used anywhere any more
    grade_fk = models.ForeignKey(Grade, verbose_name="Grade", on_delete=models.SET_NULL, null=True, blank=True)
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
        return f"{self.user.get_username()}" \
               f'{", " + str(self.semester) if self.semester else ""}' \
               f'{", " + str(self.block.name) if self.block else ""}' \
               f': {self.course}'

    # def get_absolute_url(self):
    #     return reverse('courses:list')
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
            return self.user.profile.xp_cached / days
        else:
            return 0


@receiver(post_save, sender=CourseStudent)
def coursestudent_post_save_callback(instance, **kwargs):
    """
    This model's objects are edited by teachers using the admin menu.
    If they make a manual XP adjustment we need to invalidate the user's xp_cache to recalculate xp
    """
    instance.user.profile.xp_invalidate_cache()
