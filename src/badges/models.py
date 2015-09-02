from datetime import time, date, datetime

from django.core.urlresolvers import reverse
from django.db import models
from django.templatetags.static import static
from django.utils import timezone

# Create your models here.

class BadgeType(models.Model):

    name = models.CharField(max_length=50, unique=True)
    sort_order = models.PositiveIntegerField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    repeatable = models.BooleanField(default = True)
    manual_only = models.BooleanField(default = False)
    fa_icon = models.CharField(max_length=50, blank=True, null=True,
        help_text="Name of a font-awesome icon, e.g.'fa-gift'")

    def __str__(self):
        return self.name

class BadgeSeries(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class BadgeQuerySet(models.query.QuerySet):
    def get_type(self, badge_type):
        return self.filter(badge_type = badge_type)

    def get_active(self):
        return self.filter(active = True)

class BadgeManager(models.Manager):
    def get_queryset(self):
        return BadgeQuerySet(self.model, using=self._db)

    def get_type_dicts(self):
        types = BadgeType.objects.all().order_by('sort_order')

        return {t.name : self.get_queryset().get_type(t) for t in types}

class Badge(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default = 0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    short_description = models.TextField(blank=True, null=True)
    series = models.ForeignKey(BadgeSeries, blank=True, null=True)
    badge_type = models.ForeignKey(BadgeType)
    icon = models.ImageField(upload_to='icons/badges/', blank=True, null=True) #needs Pillow for ImageField
    active = models.BooleanField(default = True)
    hours_between_repeats = models.PositiveIntegerField(default = 0)
    date_available = models.DateField(default=timezone.now)
    time_available = models.TimeField(default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True, help_text= 'only used if date_expired is blank')
    minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    maximum_XP = models.PositiveIntegerField(blank=True, null=True)

    objects = BadgeManager()

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('badges:badge_detail', kwargs={'badge_id': self.id})

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return static('img/default_icon.png')
