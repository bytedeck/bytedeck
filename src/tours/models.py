from django.conf import settings
from django.db import models


# Create your models here.
class Tour(models.Model):
    name = models.CharField(max_length=200, unique=True)
    active = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)

    # the remaining fields are the global options form bootstrap tour:
    # http://bootstraptour.com/api/
    container = models.CharField(max_length=255, null=True, blank=True)
    keyboard = models.BooleanField(default=True)
    storage = models.CharField(max_length=255, null=True, blank=True)
    debug = models.BooleanField(default=False)
    backdrop = models.BooleanField(default=False)
    backdropContainer = models.CharField(max_length=255, null=True, blank=True)
    backdropPadding = models.IntegerField(default=0)
    redirect = models.BooleanField(default=True)
    orphan = models.BooleanField(default=False)
    duration = models.IntegerField(null=True, blank=True)
    delay = models.IntegerField(null=True, blank=True)
    basePath = models.CharField(max_length=255, null=True, blank=True)
    template = models.TextField(null=True, blank=True)

    # on_start = ?

    def __str__(self):
        return self.name


class Step(models.Model):
    PLACEMENTS = (('', 'default'), ('top', 'top'), ('bottom', 'bottom'), ('left', 'left'), ('right', 'right'),)

    tour = models.ForeignKey(Tour)
    step_number = models.PositiveIntegerField(
        help_text="This value is not used directly by Bootstrap Tour, only to sort the steps.")
    # the remaining fields are the global options form bootstrap tour:
    # http://bootstraptour.com/api/
    path = models.CharField(max_length=255, null=True, blank=True)
    host = models.CharField(max_length=255, null=True, blank=True)
    element = models.CharField(max_length=255, null=True, blank=True)
    placement = models.CharField(choices=PLACEMENTS, max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    next_step = models.IntegerField(null=True, blank=True)
    prev_step = models.IntegerField(null=True, blank=True)
    animation = models.BooleanField(default=True)
    container = models.CharField(max_length=255, null=True, blank=True)
    backdrop = models.BooleanField(default=False)
    backdropContainer = models.CharField(max_length=255, null=True, blank=True)
    backdropPadding = models.IntegerField(default=0)
    # redirect = ?
    reflex = models.CharField(max_length=255, null=True, blank=True)
    orphan = models.BooleanField(default=False)
    duration = models.IntegerField(null=True, blank=True)
    delay = models.IntegerField(null=True, blank=True)
    template = models.TextField(null=True, blank=True)

    # on_show = ?

    def __str__(self):
        return str(self.tour) + " (" + str(self.step_number) + ")"

    class Meta:
        ordering = ['tour', 'step_number']
        unique_together = ("tour", "step_number")


class CompletedTour(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=False)
    tour = models.ForeignKey(Tour)
    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)


# class TourDataQuerySet(models.query.QuerySet):
#     def all_for_user(self, user):
#         return self.filter(user = user)

class TourDataManager(models.Manager):
    def get_queryset(self):
        pass
        # return UserTourDataQuerySet(self.model, using=self._db)


class TourData(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=False)

    objects = TourDataManager()
