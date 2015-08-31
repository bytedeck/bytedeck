from datetime import time, date, datetime

from django.db import models
from django.utils import timezone

# Create your models here.

class badge(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default = 0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    # tags = GenericRelation("TaggedItem", null=True, blank=True)
    # creator = models.CharField(max_length=250)
    # last_editor = models.CharField(max_length=250)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    icon = models.ImageField(upload_to='icons/badges/', blank=True, null=True) #needs Pillow for ImageField
    visible_to_students = models.BooleanField(default = True)
    max_repeats = models.IntegerField(default = 0, help_text = '0 = not repeatable, enter -1 for unlimited')
    hours_between_repeats = models.PositiveIntegerField(default = 0)
    date_available = models.DateField(default=timezone.now)
    time_available = models.TimeField(default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True, help_text= 'only used if date_expired is blank')
    minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    maximum_XP = models.PositiveIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name
