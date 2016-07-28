from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q, Max, Sum
from django.templatetags.static import static

# from django.contrib.contenttypes.models import ContentType
# from django.contrib.contenttypes import generic

from datetime import time
from django.utils import timezone

from djconfig import config

from prerequisites.models import Prereq, IsAPrereqMixin
from badges.models import BadgeAssertion
from comments.models import Comment


class Category(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "campaign"
        ordering = ["title"]

    def __str__(self):
        return self.title


class CommonData(models.Model):
    title = models.CharField(max_length=50, unique=True)
    instructions = models.TextField()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class XPItem(models.Model):
    """
    Abstract class to gather common data required of all XP granting models
    Need to get badges to use these...
    """
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default=0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    visible_to_students = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    max_repeats = models.IntegerField(default=0, help_text='0 = not repeatable, enter -1 for unlimited')
    hours_between_repeats = models.PositiveIntegerField(default=0)
    date_available = models.DateField(default=timezone.now)  # timezone aware!
    time_available = models.TimeField(default=time().min)  # midnight local time
    date_expired = models.DateField(blank=True, null=True,
                                    help_text='If both Date and Time expired are blank, then the quest never expires')
    time_expired = models.TimeField(blank=True, null=True,  # local time
                                    help_text='If Date expired is blank, expire at this time every day \
                                    and reappear at midnight. If this is blank, then midnight assumed.')
    icon = models.ImageField(upload_to='icons/', blank=True, null=True)  # needs Pillow for ImageField

    class Meta:
        abstract = True
        ordering = ["-sort_order", "-time_expired", "-date_expired", "name"]

    def __str__(self):
        return self.name

    # allow us to handle iconless items.  Use with: <img src="{{ object.icon|default_if_none:'#' }}" />
    def icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url

    def get_absolute_url(self):
        return reverse('quests:quest_detail', kwargs={'quest_id': self.id})

        # def get_icon_url(self):
        #     return "/images/s.jpg"


class QuestQuerySet(models.query.QuerySet):
    def datetime_available(self):
        now_local = timezone.now().astimezone(timezone.get_default_timezone())

        # Filter quests with available date on or before today
        qs = self.filter(date_available__lte=now_local.date())

        # Exclude quests that become available today but haven't reached the time
        return qs.exclude(Q(date_available=now_local.date()) & Q(time_available__gt=now_local.time()))

    def not_expired(self):
        """
        If date_expired and time_expired are null: quest never expires
        If date_expired exists, but time_expired is null: quest expires after the date (midnight)
        If date_expired and time_expired exist: thing expires on that date, after the time
        If only time_expired exists: thing expires after the time, daily
            (so would become not expired again at midnight when time = 00:00:00)
        :return:
        """
        # TODO: Note that these dates and times are not timezone aware!  Maybe check out the widget to fix this
        # https://docs.djangoproject.com/en/1.9/topics/i18n/timezones/

        now_tz = timezone.now()
        now_local = now_tz.astimezone(timezone.get_default_timezone())

        # Filter for quests that have EITHER no expiry date, OR an expiry date that is after today
        qs_date = self.filter(Q(date_expired=None) | Q(date_expired__gte=now_local.date()))

        # Remove quests that have the current date AND past expiry time
        qs_date = qs_date.exclude(Q(date_expired=now_local.date()) & Q(time_expired__lt=now_local.time()))

        # Remove quests with no expiry date AND past expiry time (i.e. daily expiration at set time)
        return qs_date.exclude(Q(date_expired=None) & Q(time_expired__lt=now_local.time()))

    def visible(self):
        return self.filter(visible_to_students=True)

    # TODO: this should be generic and placed in the prerequisites app
    # extend models.Model (e.g. PrereqModel) and prereq users should subclass it
    def get_conditions_met(self, user):
        """
        Takes a queryset and returns a subset of items which have had their prerequisite conditions met
        by the user
        :param user:
        :return: A queryset of the prerequisite's that have been met so far
        """
        pk_met_list = [
            obj.pk for obj in self
            if Prereq.objects.all_conditions_met(obj, user)
            ]
        return self.filter(pk__in=pk_met_list)


class QuestManager(models.Manager):
    def get_queryset(self):
        return QuestQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().datetime_available().not_expired().visible()

    def get_available(self, user, remove_hidden=True):
        qs = self.get_active().get_conditions_met(user)
        quest_list = list(qs)
        # http://stackoverflow.com/questions/1207406/remove-items-from-a-list-while-iterating-in-python
        available_quests = [q for q in quest_list if QuestSubmission.objects.quest_is_available(user, q)]
        if remove_hidden:
            available_quests = [q for q in available_quests if not user.profile.is_quest_hidden(q)]
        return available_quests


class Quest(XPItem, IsAPrereqMixin):
    verification_required = models.BooleanField(default=True,
                                                help_text="Teacher must approve submissions of this quest.  If \
                                                unchecked then submissions will automatically be approved and XP \
                                                granted without the teacher seeing the submission.")
    hideable = models.BooleanField(default=True, help_text="Students can choose to hide this quest form their list of \
                                                 available quests. ")
    categories = models.ManyToManyField(Category, blank=True)
    common_data = models.ForeignKey(CommonData, blank=True, null=True)
    instructions = models.TextField(blank=True)
    submission_details = models.TextField(blank=True)
    instructor_notes = models.TextField(blank=True, null=True,
                                        help_text="This field is only visible to Staff. \
                                        Use it to place answer keys or other notes.")

    # What does this do to help us?
    prereq_parent = GenericRelation(Prereq,
                                    content_type_field='parent_content_type',
                                    object_id_field='parent_object_id')

    prereq_prereq = GenericRelation(Prereq,
                                    content_type_field='prereq_content_type',
                                    object_id_field='prereq_object_id')

    prereq_or_prereq = GenericRelation(Prereq,
                                       content_type_field='or_prereq_content_type',
                                       object_id_field='or_prereq_object_id')

    objects = QuestManager()

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return static('img/default_icon.png')

    def prereqs(self):
        return Prereq.objects.all_parent(self)

    # TODO: Repeat of queryset code logic, how to combine?
    def expired(self):

        now_tz = timezone.now()
        now_local = now_tz.astimezone(timezone.get_default_timezone())

        # quests that have the current date AND past expiry time
        if self.date_expired and self.date_expired == now_local.date() \
                and self.time_expired and self.time_expired < now_local.time():
            return True

        # quests with no expiry date AND past expiry time (i.e.daily expiration at set time)
        if self.date_expired is None and self.time_expired and self.time_expired < now_local.time():
            return True

        if self.date_expired and self.date_expired < now_local.date():
            return True

        return False

    def is_repeat_available(self, time_of_last, ordinal_of_last):
        # if haven't maxed out repeats
        if self.max_repeats == -1 or self.max_repeats >= ordinal_of_last:
            time_since_last = timezone.now() - time_of_last
            hours_since_last = time_since_last.total_seconds() // 3600
            # and the proper amount of time has passed
            if hours_since_last >= self.hours_between_repeats:
                return True
        return False

    def condition_met_as_prerequisite(self, user, num_required=1):
        """
        Defines how this model's requirements are met as a prerequisite to other models
        :param user:
        :param num_required:
        :return: True if the condition have been met for this object.
        """
        num_approved = QuestSubmission.objects.all_for_user_quest(user, self, False).approved().count()
        # print("num_approved: " + str(num_approved) + "/" + str(num_required))
        return num_approved >= num_required

    # TODO: should be part of the prerequisite interface
    def is_prereq(self):
        """
        :return: True if this object has been assigned as a prerequisite to at least one another object.
        """
        return Prereq.objects.is_prerequisite(self)


# class Feedback(models.Model):
#     user = models.ForeignKey(User, related_name='feedback_user')
#     quest = models.ForeignKey(Quest, related_name='feedback_quest')
#     time_to_complete = models.DurationField(blank=True, null=True)
#     time_to_complete_approved = models.NullBooleanField(blank = True, null=True)
#     feedback = models.TextField(blank=True,
#         help_text = 'Did you have a suggestion that could improve this quest')
#     feedback_approved = models.NullBooleanField(blank = True, null=True)
#     datetime_submitted = models.DateTimeField(auto_now_add=True, auto_now=False)
#
#     class Meta:
#         unique_together = ('user','quest',)
#
#     def __str__(self):
#         return str(self.id)


TAG_CHOICES = (
    ("python", "python"),
    ("django", "django"),
)


# Demo of ContentType foreign key.  Model not actually in use
class TaggedItem(models.Model):
    tag = models.SlugField(choices=TAG_CHOICES)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()

    def get_absolute_url(self):
        return reverse('profile_detail', kwargs={'pk': self.pk})

    content_object = GenericForeignKey()

    def __str__(self):
        return self.tag


# QuestSubmission ###############################################

class QuestSubmissionQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user=user)

    def get_quest(self, quest):
        return self.filter(quest=quest)

    def approved(self):
        return self.filter(is_approved=True).order_by('-time_approved')

    def not_approved(self):
        return self.filter(is_approved=False)

    def completed(self):
        return self.filter(is_completed=True).order_by('-time_completed')

    def not_completed(self):
        return self.filter(is_completed=False).order_by('-time_completed')

    def has_completion_date(self):
        return self.filter(time_completed__isnull=False)

    def no_game_lab(self):
        return self.filter(game_lab_transfer=False)

    def game_lab(self):
        return self.filter(game_lab_transfer=True)

    def get_semester(self, semester):
        return self.filter(semester=semester)

    def get_not_semester(self, semester):
        return self.exclude(semester=semester)

    def get_completed_before(self, date):
        return self.filter(time_approved__lte=date)


class QuestSubmissionManager(models.Manager):
    def get_queryset(self, active_semester_only=False):
        qs = QuestSubmissionQuerySet(self.model, using=self._db)
        qs = qs.select_related('quest')
        if active_semester_only:
            return qs.get_semester(config.hs_active_semester)
        else:
            return qs

    def all_for_quest(self, quest):
        return self.get_queryset(True).get_quest(quest)

    def all_not_approved(self, user=None, active_semester_only=True):
        if user is None:
            return self.get_queryset(active_semester_only).not_approved()
        return self.get_queryset(active_semester_only).get_user(user).not_approved()

    def all_approved(self, user=None, quest=None, up_to_date=None):
        qs = self.get_queryset(True).approved()

        if user is None:
            # Staff have a separate tab for skipped quests
            qs = qs.no_game_lab()
        else:
            qs = qs.get_user(user)

        if quest is not None:
            qs = qs.get_quest(quest)

        if up_to_date is not None:
            qs = qs.get_completed_before(up_to_date)

        return qs
        #     return self.get_queryset().approved().no_game_lab()
        # return self.get_queryset().get_user(user).approved()
        #     return self.get_queryset().approved().completed().no_game_lab()
        # return self.get_queryset().get_user(user).approved().completed()

    def all_skipped(self, user=None):
        if user is None:
            return self.get_queryset(True).approved().completed().game_lab()
        return self.get_queryset(True).get_user(user).approved().completed()

    # i.e In Progress
    def all_not_completed(self, user=None, active_semester_only=True):
        if user is None:
            return self.get_queryset(active_semester_only).not_completed()
        # only returned quests will have a time completed, placing them on top
        return self.get_queryset(active_semester_only).get_user(user).not_completed()

    def all_completed_past(self, user):
        qs = self.get_queryset().get_user(user).completed()
        return qs.get_not_semester(config.hs_active_semester).order_by('is_approved', '-time_approved')

    def all_completed(self, user=None):
        if user is None:
            return self.get_queryset(True).completed()
        return self.get_queryset(True).get_user(user).completed().order_by(
            'is_approved', '-time_approved')

    def num_completed(self, user=None):
        if user is None:
            return self.get_queryset(True).completed().count()
        return self.get_queryset(True).get_user(user).completed().count()

    def all_awaiting_approval(self, user=None):
        if user is None:
            return self.get_queryset(True).not_approved().completed()
        return self.get_queryset(True).get_user(user).not_approved().completed()

    def all_returned(self, user=None):
        # completion date indicates the quest was submitted, but since completed
        # is false, it must have been returned.
        if user is None:
            returned_qs = self.get_queryset(True).not_completed().has_completion_date()
            # postgres places null values at the beginning.  This will move them to the extend
            # see: http://stackoverflow.com/questions/15121093/django-adding-nulls-last-to-query
            q = returned_qs.extra(select={'date_null': 'time_returned is null'})
            return q.extra(order_by=['date_null', '-time_returned'])
            # return returned_qs
        return self.get_queryset(True).get_user(user).not_completed().has_completion_date().order_by('-time_returned')

    def all_for_user_quest(self, user, quest, active_semester_only):
        return self.get_queryset(active_semester_only).get_user(user).get_quest(quest)

    def num_submissions(self, user, quest):
        qs = self.all_for_user_quest(user, quest, False)
        if qs.exists():
            max_dict = qs.aggregate(Max('ordinal'))
            return max_dict.get('ordinal__max')
        else:
            return 0

    def quest_is_available(self, user, quest):
        num_subs = self.num_submissions(user, quest)
        if num_subs == 0:
            return True
        # check if the quest is already in progress
        try:
            self.all_not_completed(user=user).get(quest=quest)
            # if no exception is thrown it means that an inprogress submission was found
            return False
        except MultipleObjectsReturned:
            return False  # multiple found
        except ObjectDoesNotExist:
            pass  # nothing found, continue

        latest_sub = self.all_for_user_quest(user, quest, False).latest('first_time_completed')
        latest_dt = latest_sub.first_time_completed

        # to handle cases before first_time_completed existed as a property
        if not latest_dt:
            latest_dt = latest_sub.time_completed
        return quest.is_repeat_available(latest_dt, num_subs)

    def create_submission(self, user, quest):
        if self.quest_is_available(user, quest):
            ordinal = self.num_submissions(user, quest) + 1
            new_submission = QuestSubmission(
                quest=quest,
                user=user,
                ordinal=ordinal,
                semester_id=config.hs_active_semester,
            )
            new_submission.save()
            return new_submission
        else:
            return None

    def calculate_xp(self, user):
        total_xp = self.all_approved(user).no_game_lab().aggregate(Sum('quest__xp'))
        xp = total_xp['quest__xp__sum']
        if xp is None:
            xp = 0
        return xp

    def calculate_xp_to_date(self, user, date):
        # print("submission.calculate_xp_to_date date: " + str(date))
        qs = self.all_approved(user, up_to_date=date).no_game_lab()

        total_xp = qs.aggregate(Sum('quest__xp'))
        xp = total_xp['quest__xp__sum']
        if xp is None:
            xp = 0
        return xp

    def user_last_submission_completed(self, user):
        # print( self.get_queryset().get_user(user).completed().latest('time_completed'))
        return self.get_queryset(True).get_user(user).completed().latest('time_completed')

    def move_incomplete_to_active_semester(self):
        """ Called when changing Active Semesters, however should be uneccessary
        as Closing a semester removes all incomplete quests.

        Not sure why you would need to change active semester without having
        closed other, perhaps to look at old quests?

        Either way, this prevents them from getting stuck in an inactive semester
        """
        # submitted but not accepted
        qs = self.all_not_approved(active_semester_only=False)
        # print("NOT APPROVED ********")
        # print(qs)
        for sub in qs:
            sub.semester_id = config.hs_active_semester
            sub.save()

        # started but not submitted
        qs = self.all_not_completed(active_semester_only=False)
        # print("NOT COMPLETED ********")
        # print(qs)
        for sub in qs:
            sub.semester_id = config.hs_active_semester
            sub.save()

    def remove_in_progress(self):
        # In Progress Quests
        qs = self.all_not_completed(active_semester_only=False)
        num_del = qs.delete()
        return num_del


class QuestSubmission(models.Model):
    quest = models.ForeignKey(Quest)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             related_name="quest_submission_user")
    ordinal = models.PositiveIntegerField(default=1,
                                          help_text='indicating submissions beyond the first for repeatable quests')
    is_completed = models.BooleanField(default=False)
    first_time_completed = models.DateTimeField(null=True, blank=True)
    time_completed = models.DateTimeField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    time_approved = models.DateTimeField(null=True, blank=True)
    time_returned = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated = models.DateTimeField(auto_now=True, auto_now_add=False)
    # all references to gamelab changed to "skipped"
    game_lab_transfer = models.BooleanField(default=False, help_text='XP not counted')
    semester = models.ForeignKey('courses.Semester')

    class Meta:
        ordering = ["time_approved", "time_completed"]

    objects = QuestSubmissionManager()

    def __str__(self):
        if self.ordinal > 1:
            ordinal_str = " (" + str(self.ordinal) + ")"
        else:
            ordinal_str = ""
        return self.quest.name + ordinal_str

    def get_absolute_url(self):
        return reverse('quests:submission', kwargs={'submission_id': self.id})

    def mark_completed(self):
        self.is_completed = True
        self.time_completed = timezone.now()
        # this is only set the first time, so it can be referenced to
        # when calculating repeatable quests
        if self.first_time_completed is not None:
            self.first_time_completed = timezone.now()
        self.save()

    def mark_approved(self, transfer=False):
        self.is_completed = True  # might have been false if returned
        self.is_approved = True
        self.time_approved = timezone.now()
        self.game_lab_transfer = transfer
        self.save()
        # update badges
        BadgeAssertion.objects.check_for_new_assertions(self.user, transfer=transfer)

    def mark_returned(self):
        self.is_completed = False
        self.is_approved = False
        self.game_lab_transfer = False
        self.time_returned = timezone.now()
        self.save()

    def is_awaiting_approval(self):
        return self.is_completed and not self.is_approved

    def is_returned(self):
        return self.time_completed is not None and not self.is_completed

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)
