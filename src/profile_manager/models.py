from django.db import models
from django.conf import settings
from django.core.urlresolvers import reverse

from quest_manager.models import Course

from datetime import datetime

# GRAD_YEAR_CHOICES = []
# for r in range(datetime.now().year, datetime.now().year+4):
#         GRAD_YEAR_CHOICES.append((r,r)) #(actual value, human readable name) tuples

class Profile(models.Model):

    def get_grad_year_choices():
        grad_year_choices = []
        for r in range(datetime.now().year, datetime.now().year+4):
                grad_year_choices.append((r,r)) #(actual value, human readable name) tuples
        return grad_year_choices

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile_user", null=False)
    alias = models.CharField(max_length=50, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, null=False, blank=False)
    last_name = models.CharField(max_length=50, null=False, blank=False)
    preferred_name = models.CharField(max_length=50, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    student_number = models.PositiveIntegerField(unique=True, blank=False, null=False)
    grad_year = models.PositiveIntegerField(choices=get_grad_year_choices())
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)

class Rank(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp_min = models.PositiveIntegerField(unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)

class UserCourse(models.Model):

    SEMESTER_CHOICES = ((1,1),(2,2),)
    BLOCK_CHOICES = (('A','A'),('B','B'),('C','C'),('D','D'),)

    def get_current_school_year():
        #if it is currently beyond August, go 2016/17 else got 2015/16
        year_first = datetime.now()
        if datetime.now().month > 7 :
            year_first = year_first.replace(year = year_first.year + 1)
        year_second = year_first.replace(year = year_first.year + 1)
        return year_first.strftime("%Y/") + year_second.strftime("%y")

    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    school_year = models.CharField(max_length = 7, default = get_current_school_year())
    semester = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
    block = models.CharField(max_length=1, choices=BLOCK_CHOICES)
    course_on_timetable = models.ForeignKey(Course, help_text = 'The course your are registered for in your timetable')



    # alias = models.CharField(max_length=50, unique=True, null=True, blank=True)
    # first_name = models.CharField(max_length=50, null=False, blank=False)
    # last_name = models.CharField(max_length=50, null=False, blank=False)
    # preferred_name = models.CharField(max_length=50, null=True, blank=True)
    # avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    # student_number = models.PositiveIntegerField(unique=True, blank=False, null=False)
    # grad_year = models.PositiveIntegerField(choices=YEAR_CHOICES)
    # datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)

    # def __str__(self):
    #     return str(self.user + ":")
