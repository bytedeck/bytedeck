from django.db import models
from django.contrib.auth.models import User
# from django.contrib.contenttypes.models import ContentType
# from django.contrib.contenttypes import generic

from datetime import time, date
from django.utils import timezone

class Category(models.Model):
    category = models.CharField(max_length=50, unique=True, blank=False)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.category



class XPItem(models.Model):
    name = models.CharField(max_length=50, unique=True, blank=False)
    xp = models.PositiveIntegerField(default = 0, blank=True, null=False)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    # creator = models.CharField(max_length=250)
    # last_editor = models.CharField(max_length=250)
    short_description = models.TextField(max_length=250, blank=True)
    visible_to_students = models.BooleanField(default = True, null=False)
    max_repeats = models.IntegerField(default = 0, blank=True, null=False,
        help_text = '0 = not repeatable, -1 = unlimited')
    hours_between_repeats = models.PositiveIntegerField(default = 0, blank=True, null=False)
    date_available = models.DateField(blank=False, null=False, default=timezone.now)
    time_available = models.TimeField(blank=False, null=False, default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True)
    minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    maximum_XP = models.PositiveIntegerField(blank=True, null=True)
    # prerequisites = generic.GenericRelation(Prerequisite)
    # prerequisites_advanced = models.CharField(max_length=250)
    icon = models.FileField(upload_to='icons/', null=True)
    # icon = models.ImageField(upload_to='icons/', null=True) #needs Pillow for ImageField

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

class Quest(XPItem):
    verification_required = models.BooleanField(default = True, null=False)
    category = models.ForeignKey(Category, blank=False, null=False)
    instructions = models.TextField(blank=True)
    submission_details = models.TextField(blank=True)

class Feedback(models.Model):
    user = models.ForeignKey(User, blank=False, null=False, related_name='feedback_user')
    quest = models.ForeignKey(Quest, blank=False, null=False, related_name='feedback_quest')
    time_to_complete = models.DurationField(blank=True, null=True)
    time_to_complete_approved = models.NullBooleanField(blank = True, null=True)
    feedback = models.TextField(blank=True,
        help_text = 'Did you have a suggestion that could improve this quest')
    feedback_approved = models.NullBooleanField(blank = True, null=True)
    datetime_submitted = models.DateTimeField(auto_now_add=True, auto_now=False)

    class Meta:
        unique_together = ('user','quest',)

    def __str__(self):
        return str(self.id)

class Prerequisite(models.Model):
    parent_quest = models.ForeignKey(Quest, blank=False, null=False)
    # Generic relations:
    # https://docs.djangoproject.com/en/1.4/ref/contrib/contenttypes/#generic-relations
    # content_type = models.ForeignKey(ContentType)
    # object_id = models.PositiveIntegerField()
    # content_object = generic.GenericForeignKey('content_type', 'object_id')
    prerequisite_item = models.ForeignKey(Quest, related_name='prerequisite_item')
    invert_prerequisite = models.BooleanField(default = False, null=False,
        help_text = 'item is available if user does NOT have this pre-requisite')
    alternate_prerequisite_item_1 = models.ForeignKey(Quest, related_name='alternate_prerequisite_item_1',
        help_text = 'user must have one of the prerequisite items', blank=True, null=True)
    invert_alt_prerequisite_1 = models.BooleanField(default = False, null=False,
        help_text = 'item is available if user does NOT have this pre-requisite')
    alternate_prerequisite_item_2 = models.ForeignKey(Quest, related_name='alternate_prerequisite_item_2',
        help_text = 'user must have one of the prerequisite items', blank=True, null=True)
    invert_alt_prerequisite_2 = models.BooleanField(default = False, null=False,
        help_text = 'item is available if user does NOT have this pre-requisite')
    # minimum_rank =
    # maximum_rank =

    # def __str__(self):
    #     return self.category
