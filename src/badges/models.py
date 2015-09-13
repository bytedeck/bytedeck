from datetime import time, date, datetime

from django.contrib.auth.models import User
from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Max, Sum
from django.templatetags.static import static
from django.utils import timezone

from prerequisites.models import Prereq
from notifications.signals import notify

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

    class Meta:
        ordering = ['sort_order']

class BadgeSeries(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Badge Series'"

class BadgeQuerySet(models.query.QuerySet):
    def get_type(self, badge_type):
        return self.filter(badge_type = badge_type)

    def get_active(self):
        return self.filter(active = True)

class BadgeManager(models.Manager):
    def get_queryset(self):
        return BadgeQuerySet(self.model, using=self._db).order_by('-sort_order')

    def user_earned_badges(self, user):
        return list(
                set(
                  [
                    ass.badge for ass in BadgeAssertion.objects.filter(user=user).all()
                  ]
                )
               )

    def get_type_dicts(self):
        types = BadgeType.objects.all()
        return [
                    {
                        'badge_type': t,
                        'list': self.get_queryset().get_type(t)
                    } for t in types
                ]


    #this should be generic and placed in the prerequisites app
    # extend models.Model (e.g. PrereqModel) and prereq users should subclass it
    def get_conditions_met(self, user):
        pk_met_list = [
                obj.pk for obj in self.get_queryset()
                if not obj.badge_type.manual_only and Prereq.objects.all_conditions_met(obj, user)
                ]
        return self.filter(pk__in = pk_met_list)

class Badge(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default = 0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    short_description = models.TextField(blank=True, null=True)
    series = models.ForeignKey(BadgeSeries, blank=True, null=True)
    badge_type = models.ForeignKey(BadgeType)
    icon = models.ImageField(upload_to='icons/badges/', blank=True, null=True) #needs Pillow for ImageField
    sort_order = models.PositiveIntegerField(blank=True, null=True)
    active = models.BooleanField(default = True)
    hours_between_repeats = models.PositiveIntegerField(default = 0)
    date_available = models.DateField(default=timezone.now)
    time_available = models.TimeField(default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True, help_text= 'only used if date_expired is blank')
    minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    maximum_XP = models.PositiveIntegerField(blank=True, null=True)

    objects = BadgeManager()

    class Meta:
        order_with_respect_to = 'badge_type'
        ordering = ['name']

    def __str__(self):
        return self.name

    def prereqs(self):
        return Prereq.objects.all_parent(self)

    def get_absolute_url(self):
        return reverse('badges:list')

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return static('img/default_icon.png')

    # to help with the prerequisite choices!
    @staticmethod
    def autocomplete_search_fields():
        return ("name__icontains",)

    # all models that want to act as a possible prerequisite need to have this method
    # Create a default in the PrereqModel(models.Model) class that uses a default:
    # prereq_met boolean field.  Use that or override the method like this
    def condition_met_as_prerequisite(self, user, num_required):
        num_approved = BadgeAssertion.objects.all_for_user_badge(user, self).count()
        # print("num_approved: " + str(num_approved) + "/" + str(num_required))
        return num_approved >= num_required


class BadgeAssertionQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user = user)

    def get_badge(self, badge):
        return self.filter(badge = badge)

    def get_type(self, badge_type):
        return self.filter(badge__badge_type = badge_type)

class BadgeAssertionManager(models.Manager):
    def get_queryset(self):
        return BadgeAssertionQuerySet(self.model, using=self._db)

    def all_for_user_badge(self, user, badge):
        return self.get_queryset().get_user(user).get_badge(badge)

    def num_assertions(self, user, badge):
        qs = self.all_for_user_badge(user, badge)
        if qs.exists():
            max_dict = qs.aggregate(Max('ordinal'))
            return max_dict.get('ordinal__max')
        else:
            return 0

    def get_assertion_ordinal(self, user, badge):
        return self.num_assertions(user, badge) + 1

    def create_assertion(self, user, badge, issued_by=None):
        ordinal = self.get_assertion_ordinal(user, badge)
        new_assertion = BadgeAssertion(
            badge = badge,
            user = user,
            ordinal = ordinal,
            issued_by = issued_by,
        )
        new_assertion.save()

        if issued_by==None:
            issued_by=User.objects.filter(is_staff=True).first()

        notify.send(
            issued_by, #sender
            # action=...,
            target=new_assertion.badge,
            recipient=user,
            affected_users=[user,],
            icon="<i class='fa fa-lg fa-fw fa-trophy text-warning'></i>",
            verb='granted you the achievement')

        return new_assertion

    def check_for_new_assertions(self, user):

        badges = Badge.objects.get_conditions_met(user)
        for badge in badges:
            #if the badge doesn't already exist
            if not self.all_for_user_badge(user, badge):
                self.create_assertion(user, badge)


    def get_by_type_for_user(self, user):
        self.check_for_new_assertions(user)
        types = BadgeType.objects.all()
        qs = self.get_queryset().get_user(user)
        by_type =  [
                    {
                        'badge_type': t,
                        'list': qs.get_type(t)
                    } for t in types
                ]
        return by_type

    def calculate_xp(self, user):
        # self.check_for_new_assertions(user)
        total_xp = self.get_queryset().get_user(user).aggregate(Sum('badge__xp'))
        xp = total_xp['badge__xp__sum']
        if xp is None:
            xp = 0
        return xp


class BadgeAssertion(models.Model):
    badge = models.ForeignKey(Badge)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    ordinal = models.PositiveIntegerField(default = 1, help_text = 'indicating the nth time user has received this badge')
    # time_issued = models.DateTimeField(default = timezone.now)
    timestamp = models.DateTimeField(auto_now=True, auto_now_add=False)
    updated = models.DateTimeField(auto_now=False, auto_now_add=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='issued_by')

    objects = BadgeAssertionManager()

    def __str__(self):
        ordinal_str = ""
        if self.ordinal > 1:
            ordinal_str = " (" + str(self.ordinal) + ")"
        return self.badge.name + ordinal_str

    def get_absolute_url(self):
        return reverse('badges:list')

    # def grant(self, user):
        # self.is_completed = True
        # self.time_issued = timezone.now()
        # self.save()

    # def revoke(self):
        # self.is_completed = False
        # self.is_approved = False
        # self.save()

    # def get_comments(self):
    #     return Comment.objects.all_with_target_object(self)
