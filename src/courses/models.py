from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.db import models

from djconfig import config

from quest_manager.models import QuestSubmission

from datetime import timedelta, date

from workdays import networkdays, workday

# Create your models here.
class RankQuerySet(models.query.QuerySet):
    def get_ranks_lte(self, xp):
        return self.filter(xp__lte = xp)

    def get_ranks_gt(self, xp):
        return self.filter(xp__gt = xp)

class RankManager(models.Manager):
    def get_queryset(self):
        return RankQuerySet(self.model, using=self._db).order_by('xp')

    def get_rank(self, user_xp=0):
        return self.get_queryset().get_ranks_lte(user_xp).last()

    def get_next_rank(self, user_xp=0):
        return self.get_queryset().get_ranks_gt(user_xp).first()

class Rank(models.Model):
    name = models.CharField(max_length=50, unique=False, null=True)
    xp = models.PositiveIntegerField(help_text='The XP at which this rank is granted')
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    fa_icon = models.TextField(null=True, blank=True,
        help_text='html to render a font-awesome icon or icon stack etc.')

    objects = RankManager()


    class Meta:
        ordering = ['xp']

    def __str__(self):
        return self.name

    # to help with the prerequisite choices!
    @staticmethod
    def autocomplete_search_fields():
        return ("name__icontains",)

    # all models that want to act as a possible prerequisite need to have this
    # method. Create a default in the PrereqModel(models.Model) class that uses
    # a default prereq_met boolean field.  Use that or override the method like
    # this
    def condition_met_as_prerequisite(self, user, num_required):
        #num_required is not used for this one
        # profile = Profile.objects.get(user=user)
        return user.profile.xp() >= self.xp

class SemesterManager(models.Manager):
    def get_queryset(self):
        return models.query.QuerySet(self.model, using=self._db).order_by('-first_day')

    def get_current(self, as_queryset = False):
        if as_queryset:
            return self.get_queryset().filter(pk = config.hs_active_semester)
        else:
            return self.get_queryset().get(pk = config.hs_active_semester)

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

        #There are still quests awaiting approval, can't close!
        if QuestSubmission.objects.all_awaiting_approval():
            return -2

        # need to calculate all user XP and store in their Course
        CourseStudent.objects.calc_semester_grades(active_sem)

        QuestSubmission.objects.remove_in_progress()

        active_sem.closed = True
        active_sem.save()

        return active_sem


class Semester(models.Model):
    SEMESTER_CHOICES = ((1,1),(2,2),)

    number = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
    first_day = models.DateField(blank=True, null=True)
    last_day = models.DateField(blank=True, null=True)
    active = models.BooleanField(default=False)
    closed = models.BooleanField(default=False,
        help_text="All student courses in this semester have been closed \
        and final marks recorded.")

    objects = SemesterManager()

    class Meta:
        get_latest_by = "first_day"
        ordering = ['first_day']

    def __str__(self):
        return self.first_day.strftime("%b-%Y")

    def active_by_date(self):
        return (self.last_day+timedelta(days=5)) > timezone.now().date() and (self.first_day-timedelta(days=20)) < timezone.now().date()

    def num_days(self, upto_today = False):
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
        return current_days/total_days

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

    def chillax_line_started(self):
        #return timezone.now().date() > self.get_interim1_date()
        return config.hs_chillax_line_active

    def chillax_line(self):
        return 1000 * config.hs_chillax_line * self.fraction_complete()

class DateType(models.Model):
    date_type = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.date_type


class Block(models.Model):
    block = models.CharField(max_length=50, unique=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)

    def __str__(self):
        return self.block

class ExcludedDate(models.Model):
    semester = models.ForeignKey(Semester)
    date_type = models.ForeignKey(DateType)
    date = models.DateField(unique=True)

    def __str__(self):
        return self.date.strftime("%d-%b-%Y")


class Course(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["title"]

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

    #for current active semester
    def calculate_xp(self, user):
        xp = 0
        studentcourses = self.current_courses(user)
        if studentcourses:
            for studentcourse in studentcourses:
                xp += studentcourse.xp_adjustment
        return xp

    #pick one of the courses...for now
    def current_course(self, user):
        return self.all_for_user(user).get_semester(config.hs_active_semester).first()

    def current_courses(self, user):
        return self.all_for_user(user).get_semester(config.hs_active_semester)

    def calc_semester_grades(self, semester):
        coursestudents = self.get_queryset().get_semester(semester)
        for coursestudent in coursestudents:
            coursestudent.final_xp = coursestudent.user.profile.xp_per_course()
            coursestudent.active = False
            coursestudent.save()


class CourseStudent(models.Model):
    GRADE_CHOICES = ((9,9),(10,10),(11,11),(12,12),(13, 'Adult'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    semester = models.ForeignKey(Semester)
    block = models.ForeignKey(Block)
    course = models.ForeignKey(Course)
    grade = models.PositiveIntegerField(choices=GRADE_CHOICES)
    xp_adjustment = models.IntegerField(default = 0)
    xp_adjust_explanation = models.CharField(max_length=255, blank=True, null=True)
    final_xp = models.PositiveIntegerField(blank=True, null=True)
    final_grade = models.PositiveIntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)

    objects = CourseStudentManager()

    class Meta:
        unique_together = (
                ('semester', 'block', 'user'),
                ('user','course','grade'),
            )
        verbose_name = "Student Course"
        ordering = ['semester', 'block']

    def __str__(self):
        return self.user.username + ", " + str(self.semester) + ", "  + self.block.block

    def get_absolute_url(self):
        return reverse('courses:list')
        # return reverse('courses:detail', kwargs={'pk': self.pk})

    def calc_mark(self, xp):
        fraction_complete = self.semester.fraction_complete()
        if fraction_complete > 0:
            return xp/fraction_complete/10.0
        else:
            return 0

    def xp_per_day_ave(self):
        days = self.semester.days_so_far()
        if days > 0:
            return self.user.profile.xp()/self.semester.days_so_far()
        else:
            return 0
