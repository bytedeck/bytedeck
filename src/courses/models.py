from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.db import models

from datetime import timedelta

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

    # all models that want to act as a possible prerequisite need to have this method
    # Create a default in the PrereqModel(models.Model) class that uses a default:
    # prereq_met boolean field.  Use that or override the method like this
    def condition_met_as_prerequisite(self, user, num_required):
        #num_required is not used for this one
        profile = Profile.objects.get(user=user)
        return profile.xp > self.xp

class SemesterManager(models.Manager):
    def get_queryset(self):
        return models.query.QuerySet(self.model, using=self._db).order_by('-first_day')

    def get_current(self):
        qs = self.get_queryset()
        # create a list from the slice, then filter
        #slicing can cause problems if the queryset gets filtered again
        # see: http://stackoverflow.com/questions/27560131/assertionerror-cannot-filter-a-query-once-a-slice-has-been-taken
        valid_ids = qs.values_list('pk', flat=True)[:1] #only the top one
        return qs.filter(pk__in=valid_ids)


class Semester(models.Model):
    SEMESTER_CHOICES = ((1,1),(2,2),)

    number = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
    first_day = models.DateField(blank=True, null=True)
    last_day = models.DateField(blank=True, null=True)
    active = models.BooleanField(default=True)

    objects = SemesterManager()

    class Meta:
        get_latest_by = "first_day"
        ordering = ['first_day']

    def __str__(self):
        return self.first_day.strftime("%b-%Y")

    def active_by_date(self):
        return (self.last_day+timedelta(days=5)) > timezone.now().date() and (self.first_day-timedelta(days=20)) < timezone.now().date()

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

class CourseStudentQuerySet(models.query.QuerySet):
    def sticky(self):
        return self.filter(sticky=True)

    def get_user(self, user):
        return self.filter(user=user)

    def get_semester(self, semester):
        return self.filter(semester=semester)

class CourseStudentManager(models.Manager):
    def get_queryset(self):
        return CourseStudentQuerySet(self.model, using=self._db)

    def all_for_user_semester(self, user, semester):
        return self.get_queryset().get_user(user).get_semester(semester)

    def all_for_user(self, user):
        return self.get_queryset().get_user(user)

class CourseStudent(models.Model):
    GRADE_CHOICES = ((9,9),(10,10),(11,11),(12,12),(13, 'Adult'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    semester = models.ForeignKey(Semester)
    block = models.ForeignKey(Block)
    course = models.ForeignKey(Course)
    grade = models.PositiveIntegerField(choices=GRADE_CHOICES)
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
