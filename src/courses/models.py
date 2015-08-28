from django.conf import settings
from django.core.urlresolvers import reverse

from django.db import models

# Create your models here.
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

    def __str__(self):
        return self.first_day.strftime("%b-%Y")

    objects = SemesterManager()

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
        return self.get_queryset.get_user(user).get_semester(semester)

class CourseStudent(models.Model):
    GRADE_CHOICES = ((9,9),(10,10),(11,11),(12,12),(13, 'Adult'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    semester = models.ForeignKey(Semester)
    block = models.ForeignKey(Block)
    course = models.ForeignKey(Course)
    grade = models.PositiveIntegerField(choices=GRADE_CHOICES)
    active = models.BooleanField(default=True)

    objects = CourseStudentManager()

    class Meta:
        unique_together = (
                ('semester', 'block', 'user'), 
                ('user','course','grade'),
            )

    def __str__(self):
        return self.user.username + ", " + str(self.semester) + ", "  + self.block.block

    def get_absolute_url(self):
        return reverse('courses:list')
        # return reverse('courses:detail', kwargs={'pk': self.pk})
