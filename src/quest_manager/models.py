from django.db import models

# Create your models here.
class XPItem(models.Model):
    name = models.CharField(max_length=50, unique=True, blank=False)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    # creator = models.CharField(max_length=250)
    # last_editor = models.CharField(max_length=250)
    short_description = models.TextField(max_length=250, blank=True)
    xp = models.PositiveIntegerField(default = 0, blank=True, null=False)
    visible_to_students = models.BooleanField(default = True, null=False)
    max_repeats = models.IntegerField(default = 0, blank=True, null=False,
        help_text = '0 = not repeatable, -1 = unlimited')
    hours_between_repeats = models.PositiveIntegerField(default = 0, blank=True, null=False)
    # category = models.CharField(max_length=250)
    date_available = models.DateField(blank=True, null=True)
    time_available = models.TimeField(blank=True, null=True)
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True)
    # prerequisites = models.CharField(max_length=250)
    # prerequisites_advanced = models.CharField(max_length=250)
    # icon = models.ImageField()

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

class Quest(XPItem):
    instructions = models.TextField(blank=True)
    submission_details = models.TextField(blank=True)
    verification_required = models.BooleanField(default = True, null=False)
