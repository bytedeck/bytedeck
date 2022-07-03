import uuid
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Max, Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse

from django.dispatch import receiver
from django.db.models.signals import post_save

from siteconfig.models import SiteConfig
from notifications.signals import notify

from prerequisites.models import Prereq, IsAPrereqMixin, HasPrereqsMixin


# Create your models here.

class BadgeRarityManager(models.Manager):
    def get_rarity(self, percentile):
        """Because this model is sorted by rarity, with the rarist on top,
        the first item in the returned list will be the rarest category of the item"""
        if percentile > 100.0:
            percentile = 100
        rarities = self.get_queryset().filter(percentile__gte=percentile)
        return rarities.first()


class BadgeRarity(models.Model):
    """
    A dynamic rarity system that determines the rarity of a badge based on how often it has been granted.
        A default setup might look something like this:
        Legendary, 1.0%, gold
        Epic, 5.0%, purple
        Rare, 15.0%, blue
        Common, 100%, gray
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="The unique name or label for this rarity of badge, e.g. 'Legendary'",
    )
    percentile = models.FloatField(
        unique=True,
        help_text="A number from 0.1% (or less) to 100.0% indicating the rarity of the badge.  For example: \
            10.0% would mean badges that <10.0% of users have earned will be assigned this rarity, unless \
            it falls into the next more rare category (such as 5.0%).  A value of 100 will catch all badges."
    )
    color = models.CharField(
        max_length=50,
        default='gray',
        help_text='An HTML color name "gray" or hex value in the format: "#7b7b7b;"',
    )
    fa_icon = models.CharField(
        max_length=50,
        default='fa-certificate',
        help_text='A font-awesome icon to represent this rarity, should begin with "fa-".  See here for \
            options: "https://faicons.com"'
    )

    objects = BadgeRarityManager()

    class Meta:
        ordering = ['percentile']
        verbose_name = "Badge Rarity"
        verbose_name_plural = "Badge Rarities"

    def __str__(self):
        return self.name

    def get_icon_html(self):
        icon = "<i class='fa {} fa-fw rarity-{}' title='{}' style='color:{}' aria-hidden='true'></i>".format(
            self.fa_icon,
            self.name,
            self.name,
            self.color,
        )
        aria_span = "<span class='sr-only'>{}</span>".format(self.name)
        return icon + aria_span


class BadgeType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    sort_order = models.PositiveIntegerField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    repeatable = models.BooleanField(default=True)
    # manual_only = models.BooleanField(default = False)
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
        return self.filter(badge_type=badge_type)

    def get_active(self):
        return self.filter(active=True)


class BadgeManager(models.Manager):
    def get_queryset(self):
        return BadgeQuerySet(self.model, using=self._db).order_by('sort_order')

    # this should be generic and placed in the prerequisites app
    # extend models.Model (e.g. PrereqModel) and prereq users should subclass it
    def get_conditions_met(self, user):
        pk_met_list = [
            obj.pk for obj in self.get_queryset().get_active()
            if Prereq.objects.all_conditions_met(obj, user, False)
            # if not obj.badge_type.manual_only and Prereq.objects.all_conditions_met(obj, user)
        ]
        return self.filter(pk__in=pk_met_list)

    def all_manually_granted(self):
        # build a list of pk's for badges that have no prerequisites.
        pk_manual_list = [
            obj.pk for obj in self.get_queryset()
            if Prereq.objects.all_parent(obj).count() == 0
        ]
        return self.filter(pk__in=pk_manual_list).order_by('name')


class Badge(IsAPrereqMixin, HasPrereqsMixin, models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default=0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    short_description = models.TextField(blank=True, null=True)
    series = models.ForeignKey(BadgeSeries, blank=True, null=True, on_delete=models.SET_NULL)
    badge_type = models.ForeignKey(BadgeType, on_delete=models.PROTECT)
    icon = models.ImageField(upload_to='icons/badges/', blank=True, null=True)  # needs Pillow for ImageField
    sort_order = models.PositiveIntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)

    import_id = models.UUIDField(
        default=uuid.uuid4, unique=True,
        help_text="Only edit this if you want to link to a badge in another system so that "
                  "when importing from that other system, it will update this badge too. "
                  "Otherwise do not edit this or it will break existing links!"
    )

    map_transition = models.BooleanField(
        default=False, 
        help_text='Break maps at this badge.  This badge will link to a new map.'
    )
    # hours_between_repeats = models.PositiveIntegerField(default = 0)
    # date_available = models.DateField(default=timezone.now())
    # time_available = models.TimeField(default=time().min) # midnight
    # date_expired = models.DateField(blank=True, null=True)
    # time_expired = models.TimeField(blank=True, null=True, help_text= 'only used if date_expired is blank')
    # minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    # maximum_XP = models.PositiveIntegerField(blank=True, null=True)

    objects = BadgeManager()

    class Meta:
        # order_with_respect_to = 'badge_type'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('badges:badge_detail', kwargs={'badge_id': self.id})

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return SiteConfig.get().get_default_icon_url()

    # @cached_property
    def fraction_of_active_users_granted_this(self):
        num_assertions = BadgeAssertion.objects.filter(badge=self).count()
        return num_assertions / User.objects.filter(is_active=True).count()

    def percent_of_active_users_granted_this(self):
        return self.fraction_of_active_users_granted_this() * 100

    def get_rarity_icon(self):
        percentile = self.percent_of_active_users_granted_this()
        badge_rarity = BadgeRarity.objects.get_rarity(percentile)
        if badge_rarity:
            return badge_rarity.get_icon_html()
        else:
            return ""

    # all models that want to act as a possible prerequisite need to have this method
    # Create a default in the PrereqModel(models.Model) class that uses a default:
    # prereq_met boolean field.  Use that or override the method like this
    def condition_met_as_prerequisite(self, user, num_required=1):
        num_approved = BadgeAssertion.objects.all_for_user_badge(user, self, False).count()
        # print("num_approved: " + str(num_approved) + "/" + str(num_required))
        return num_approved >= num_required


class BadgeAssertionQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user=user)

    def get_badge(self, badge):
        return self.filter(badge=badge)

    def get_type(self, badge_type):
        return self.filter(badge__badge_type=badge_type)

    def grant_xp(self):
        return self.filter(do_not_grant_xp=False)

    def get_semester(self, semester):
        return self.filter(semester=semester)

    def get_issued_before(self, date):
        return self.filter(timestamp__lte=date)


class BadgeAssertionManager(models.Manager):
    def get_queryset(self, active_semester_only=False):
        qs = BadgeAssertionQuerySet(self.model, using=self._db)
        if active_semester_only:
            return qs.get_semester(SiteConfig.get().active_semester)
        else:
            return qs

    def all_for_user_badge(self, user, badge, active_semester_only):
        return self.get_queryset(active_semester_only).get_user(user).get_badge(badge)

    def all_for_user(self, user):
        return self.get_queryset(True).get_user(user)

    def all_for_user_distinct(self, user):
        """
        This only works in a postgresql database, but the app is designed around postgres
        https://docs.djangoproject.com/en/1.10/ref/models/querysets/#distinct
        """
        return self.get_queryset(False).get_user(user).order_by('badge_id').distinct('badge')

    def badge_assertions_dict_items(self, user):
        earned_assertions = self.all_for_user_distinct(user)
        assertion_dict = defaultdict(list)
        for assertion in earned_assertions:
            assertion_dict[assertion.badge.badge_type].append(assertion)

        return assertion_dict.items()

    def num_assertions(self, user, badge, active_semester_only=False):
        qs = self.all_for_user_badge(user, badge, active_semester_only)
        if qs.exists():
            max_dict = qs.aggregate(Max('ordinal'))
            return max_dict.get('ordinal__max')
        else:
            return 0

    def get_assertion_ordinal(self, user, badge):
        return self.num_assertions(user, badge) + 1

    def create_assertion(self, user, badge, issued_by=None, transfer=False, active_semester=None):
        ordinal = self.get_assertion_ordinal(user, badge)
        if issued_by is None:
            issued_by = get_object_or_404(User, pk=SiteConfig.get().deck_ai.pk)

        if not active_semester:
            active_semester = SiteConfig.get().active_semester.id

        new_assertion = BadgeAssertion(
            badge=badge,
            user=user,
            ordinal=ordinal,
            issued_by=issued_by,
            do_not_grant_xp=transfer,
            semester_id=active_semester
        )
        new_assertion.save()
        user.profile.xp_invalidate_cache()  # recalculate user's XP
        return new_assertion

    def check_for_new_assertions(self, user, transfer=False):
        badges = Badge.objects.get_conditions_met(user)
        for badge in badges:
            # if the badge doesn't already exist
            if not self.all_for_user_badge(user, badge, False):
                self.create_assertion(user, badge, None, transfer)
                # if a new badge has been granted, then check again recursively.
                # maybe this should be celeried?
                self.check_for_new_assertions(user, transfer)

    def get_by_type_for_user(self, user):
        self.check_for_new_assertions(user)
        types = BadgeType.objects.all()
        qs = self.get_queryset(True).get_user(user)
        by_type = [
            {
                'badge_type': t,
                'list': qs.get_type(t)
            } for t in types
        ]
        return by_type

    def calculate_xp(self, user):
        # self.check_for_new_assertions(user)
        total_xp = self.get_queryset(True).grant_xp().get_user(user).aggregate(Sum('badge__xp'))
        xp = total_xp['badge__xp__sum']
        if xp is None:
            xp = 0
        return xp

    def calculate_xp_to_date(self, user, date):
        # self.check_for_new_assertions(user)
        qs = self.get_queryset(True).grant_xp().get_user(user)
        qs = qs.get_issued_before(date)
        total_xp = qs.aggregate(Sum('badge__xp'))
        xp = total_xp['badge__xp__sum']
        if xp is None:
            xp = 0
        return xp


class BadgeAssertion(models.Model):
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ordinal = models.PositiveIntegerField(default=1, help_text='indicating the nth time user has received this badge')
    # time_issued = models.DateTimeField(default = timezone.now())
    timestamp = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated = models.DateTimeField(auto_now=True, auto_now_add=False)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='issued_by',
                                  on_delete=models.SET_NULL)
    do_not_grant_xp = models.BooleanField(default=False, help_text='XP not counted')
    semester = models.ForeignKey('courses.Semester', default=1, on_delete=models.SET_DEFAULT)

    objects = BadgeAssertionManager()

    def __str__(self):
        # ordinal_str = ""
        # if self.ordinal > 1:
        #     ordinal_str = " (" + str(self.ordinal) + ")"
        return self.badge.name  # + ordinal_str

    def get_absolute_url(self):
        return reverse('badges:list')

    def count(self):
        """Get the number of assertions with the same badge and user."""
        return BadgeAssertion.objects.num_assertions(self.user, self.badge)

    def count_bootstrap_badge(self):
        """Get the number of assertions with the same badge and user. But if
        there is <2, return "" so that it won't appear when used in
        Bootstrap Badges: http://getbootstrap.com/components/#badges
        """
        count = self.count()
        if count < 2:
            return ""
        return count

    def get_duplicate_assertions(self):
        """A qs of all assertions of this badge for this user"""
        return BadgeAssertion.objects.all_for_user_badge(self.user, self.badge, False)


# only receive signals from BadgeAssertion model
@receiver(post_save, sender=BadgeAssertion)
def post_save_receiver(sender, **kwargs):
    assertion = kwargs["instance"]
    if kwargs["created"]:
        # need an issuing object, fix this better, should be generic something "Hackerspace or "Automatic".
        sender = assertion.issued_by
        if sender is None:
            sender = User.objects.filter(is_staff=True).first()

        fa_icon = assertion.badge.badge_type.fa_icon

        if not fa_icon:
            fa_icon = "fa-certificate"

        icon = "<i class='text-warning fa fa-lg fa-fw "
        icon += fa_icon
        icon += "'></i>"

        notify.send(
            sender,
            # action= action,
            target=assertion.badge,
            recipient=assertion.user,
            affected_users=[assertion.user, ],
            icon=icon,
            verb="granted you a")
