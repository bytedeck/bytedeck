from django.db import models

# Create your models here.
class Semester(models.Model):
    SEMESTER_CHOICES = ((1,1),(2,2),)

    number = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
    first_day = models.DateField(blank=True, null=True)
    last_day = models.DateField(blank=True, null=True)

class ExcludedDate(models.Model):
    semester = models.ForeignKey(Semester)
    date_type = models.ForeignKey(DateType)
    date = models.DateField(unique=True)

class DateType(models.Model):
    date_type = models.CharField(max_length=50, unique=True)

class Block(models.Model):
    block = models.CharField(max_length=50, unique=True)

class CourseStudent(model.Models):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    semester = models.ForeignKey(Semester)
    block = models.ForeignKey(Block)
    course = models.ForeignKey(Course)
    active = models.BooleanField(default=True)

class Course(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title
