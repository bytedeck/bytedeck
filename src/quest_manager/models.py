import uuid
import json

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import models
from django.db.models import Q, Max, Sum
from django.db.models.functions import Greatest
# from django.shortcuts import get_object_or_404
# from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone, datetime_safe

from siteconfig.models import SiteConfig

from badges.models import BadgeAssertion
from comments.models import Comment
from prerequisites.models import Prereq, IsAPrereqMixin, HasPrereqsMixin, PrereqAllConditionsMet
from tags.models import TagsModelMixin
# from utilities.models import ImageResource

# from django.contrib.contenttypes.models import ContentType
# from django.contrib.contenttypes import generic


class Category(IsAPrereqMixin, models.Model):
    """ Used to group quests into 'Campaigns'
    """
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(
        default=True,
        help_text="Quests that are a part of an inactive campaign won't appear on quest maps and won't be available to students."
    )

    class Meta:
        verbose_name = "campaign"
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('quests:category_detail', kwargs={'pk': self.id})

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return SiteConfig.get().get_default_icon_url()

    def current_quests(self):
        """ Returns a queryset containing every currently available quest in this campaign."""
        return self.quest_set.all().visible().not_archived()

    def quest_count(self):
        """ Returns the total number of quests available in this campaign."""
        return self.current_quests().count()

    def xp_sum(self):
        """ Returns the total XP available from completing all visible quests in this campaign.
        Repeating quests are only counted once."""
        return self.current_quests().aggregate(Sum('xp'))['xp__sum']

    def condition_met_as_prerequisite(self, user, num_required=1):
        """
        The prerequisite is met if all quests in the campaign have been completed by the user
        param num_required: not used.
        """

        # get all the quests in this campaign/category
        quests = self.quest_set.all()

        # get all approved submissions of these quests for this user
        submissions = QuestSubmission.objects.all_approved(user=user, active_semester_only=False).filter(quest__in=quests)

        # remove duplicates with distinct so only one submission per quest is counted
        # (there could be more than one submission if there are repeatable quests in the campaign)
        submissions = submissions.order_by('quest_id').distinct('quest')

        return quests.count() == submissions.count()

    @staticmethod
    def autocomplete_search_fields():  # for grapelli prereq selection
        return ("title__icontains",)

    @staticmethod
    def gfk_search_fields():  # for AllowedGFKChoiceFiled
        return ["title__icontains"]

    @property
    def name(self):
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
    xp_can_be_entered_by_students = models.BooleanField(
        default=False,
        help_text="Allow students to enter a custom XP value for their submission of this quest. The XP field above becomes the minimum value."
    )
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    visible_to_students = models.BooleanField(
        default=True, verbose_name="published",
        help_text="If not checked, this quest will not be visible to students and will appear in your Drafts tab."
    )
    archived = models.BooleanField(
        default=False,
        help_text='Setting this will prevent it from appearing in admin quest lists.  '
        'To un-archive a quest, you will need to access it through Site Administration.'
    )
    sort_order = models.IntegerField(default=0)
    max_repeats = models.IntegerField(default=0, help_text='0 = not repeatable; -1 = unlimited repeats')
    max_xp = models.IntegerField(
        default=-1,
        help_text="The maximum amount of XP that can be gain by repeating this quest. If the Max Repeats hasn't been hit yet \
        then quest will continue to appear after this number is reached, but students will no longer \
        gain XP for completing it; -1 = unlimited"
    )
    repeat_per_semester = models.BooleanField(
        default=False,
        help_text='Repeatable once per semester, and Max Repeats becomes additional repeats per semester'
    )
    hours_between_repeats = models.PositiveIntegerField(default=0)
    date_available = models.DateField(default=timezone.localdate)  # timezone aware!
    time_available = models.TimeField(default=datetime_safe.time.min)  # midnight local time
    date_expired = models.DateField(blank=True, null=True,
                                    help_text='If both Date and Time expired are blank, then the quest never expires')
    time_expired = models.TimeField(blank=True, null=True,  # local time
                                    help_text='If Date expired is blank, expire at this time every day \
                                    and reappear at midnight. If this is blank, then midnight assumed.')
    icon = models.ImageField(upload_to='icons/', blank=True, null=True)  # needs Pillow for ImageField

    class Meta:
        abstract = True
        # manual ordering of a quest queryset places quests with smaller sort_order values above larger ones by default
        # as such, the original value for sort_order (-sort_order,) orders quests upside-down
        # the sort_order value in this list should be reverted to -sort_order once manually sorting is not necessary
        # further information can be found here: https://github.com/bytedeck/bytedeck/pull/1179
        ordering = ["sort_order", "-time_expired", "-date_expired", "name"]

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

    @property  # requiredfor prerequisite checking
    def active(self):
        """
        Available as a property to make compatible with Badge.active attribute
        :return: True if should appear to students (need to still check prereqs and previous submissions)
        """
        # XPItem is not active if it is not published (i.e. a draft = visible_to_students=False), or archived
        if not self.visible_to_students or self.archived:
            return False

        # XPItem/Quest object is inactive if it's a part of an inactive campaign
        if hasattr(self, 'campaign') and self.campaign and not self.campaign.active:
            return False

        if self.expired():
            return False

        time_now = timezone.localtime().time()
        date_now = timezone.localdate()

        # an XPItem object is inactive if its availability date is in the future
        if self.date_available > date_now:
            return False

        # an XPItem object is inactive on the day it's made available if its availability time is in the future
        if self.date_available == date_now and self.time_available > time_now:
            return False

        # If survived all the conditions, then it's active
        return True

    def is_available(self, user):
        """This quest should be in the user's available tab.  Doesn't check exactly, but same criteria.
        Should probably put criteria in one spot and share.  See QuestManager.get_available()"""

        available = (
            self.active
            and QuestSubmission.objects.not_submitted_or_inprogress(user, self)
            and Prereq.objects.all_conditions_met(self, user)
        )

        if available and not user.profile.has_current_course:
            return self.available_outside_course

        return available

    def is_repeatable(self):
        return self.max_repeats != 0


class QuestQuerySet(models.QuerySet):

    def exclude_hidden(self, user):
        """ Users can "hide" quests.  This is stored in their profile as a list of quest ids """
        return self.exclude(pk__in=user.profile.get_hidden_quests_as_list())

    def block_if_needed(self, user=None):
        """ If there are blocking quests or blocking subs in progress, only return blocking quests.
        Otherwise, return full qs """
        blocking_quests = self.filter(blocking=True)
        if user:
            # Check the student's submissions in progress.
            blocking_subs_in_progress = QuestSubmission.objects.all_not_completed(user=user, blocking=False).filter(quest__blocking=True)  # noqa
        else:
            blocking_subs_in_progress = False

        if blocking_quests or blocking_subs_in_progress:
            return blocking_quests
        else:
            return self

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
        now_local = timezone.localtime()

        # Filter for quests that have EITHER no expiry date, OR an expiry date that is after today
        qs_date = self.filter(Q(date_expired=None) | Q(date_expired__gte=now_local.date()))

        # Remove quests that have the current date AND past expiry time
        qs_date = qs_date.exclude(Q(date_expired=now_local.date()) & Q(time_expired__lt=now_local.time()))

        # Remove quests with no expiry date AND past expiry time (i.e. daily expiration at set time)
        return qs_date.exclude(Q(date_expired=None) & Q(time_expired__lt=now_local.time()))

    def visible(self):
        return self.filter(visible_to_students=True)

    def active_or_no_campaign(self):
        """With self as an argument, returns a filtered queryset
        containing only quests in active campaigns or quests without campaigns.
        """
        return self.exclude(campaign__active=False)

    def not_archived(self):
        return self.exclude(archived=True)

    def available_without_course(self):
        return self.filter(available_outside_course=True)

    # TODO: this should be generic and placed in the prerequisites app
    # extend models.Model (e.g. PrereqModel) and prereq users should subclass it
    def get_conditions_met(self, user):
        """
        Takes a queryset and returns a subset of items which have had their prerequisite conditions met
        by the user
        :param user:
        :return: A queryset of the prerequisite's that have been met so far
        """
        pk_met_list = self.get_pk_met_list(user) or [0]
        return self.filter(pk__in=pk_met_list)

    def get_list_not_submitted_or_inprogress(self, user):
        quest_list = list(self)
        # http://stackoverflow.com/questions/1207406/remove-items-from-a-list-while-iterating-in-python
        return [q for q in quest_list if QuestSubmission.objects.not_submitted_or_inprogress(user, q)]

    def not_submitted_or_inprogress(self, user):
        quest_list = self.get_list_not_submitted_or_inprogress(user)
        pk_list = [quest.id for quest in quest_list]

        # sub_pk_list = QuestSubmission.objects.not_submitted_or_inprogress(user, q).value_list('id', flat=True)
        return self.filter(pk__in=pk_list)

    def not_completed(self, user):
        """
        Exclude all quests where the user has a completed submission (whether approved or not)
        """
        completed_subs = QuestSubmission.objects.all_completed(user=user)
        return self.exclude(pk__in=completed_subs.values_list('quest__id', flat=True))

    def not_in_progress(self, user):
        """
        Exclude all quests where the user has a submission in progress,
        """
        in_progress_subs = QuestSubmission.objects.all_not_completed(user=user)
        return self.exclude(pk__in=in_progress_subs.values_list('quest__id', flat=True))

    def editable(self, user):
        if user.is_staff:
            return self
        else:
            return self.filter(editor=user.id)

    def get_pk_met_list(self, user):
        model_name = f'{Quest._meta.app_label}.{Quest._meta.model_name}'
        pk_met_list = PrereqAllConditionsMet.objects.filter(user=user, model_name=model_name).first()
        if not pk_met_list:
            from prerequisites.tasks import update_quest_conditions_for_user
            pk_met_list = update_quest_conditions_for_user(user.id)
            pk_met_list = PrereqAllConditionsMet.objects.get(id=pk_met_list)
        return json.loads(pk_met_list.ids)


class QuestManager(models.Manager):
    def get_queryset(self, include_archived=False):
        qs = QuestQuerySet(self.model, using=self._db)
        if not include_archived:
            qs = qs.not_archived()
        return qs

    def get_active(self):
        return self.get_queryset().datetime_available().not_expired().visible().active_or_no_campaign()

    def get_available(self, user, remove_hidden=True, blocking=True):
        """ Quests that should appear in the user's Available quests tab.   Should exclude:
        1. Quests whose available date & time has not past, or quest that have expired
        2. Quests that are not visible to students or archived
        3. Quests that are a part of an inactive campaign
        4. Quests whose prerequisites have not been met
        5. Quests that are not currently submitted for approval or already in progress
        6. Quests whose maximum repeats have been completed
        7. Quests whose repeat time has not passed since last completion
        8. Check for blocking quests (available and in-progress), if present, remove all others
        """
        qs = self.get_active().select_related('campaign')  # exclusions 1, 2 & 3
        qs = qs.get_conditions_met(user)  # 4
        available_quests = qs.not_submitted_or_inprogress(user)  # 5, 6 & 7

        available_quests = available_quests.block_if_needed(user=user)  # 8
        if remove_hidden:
            available_quests = available_quests.exclude_hidden(user)
        return available_quests

    def get_available_without_course(self, user):
        qs = self.get_active().get_conditions_met(user).available_without_course()
        return qs.not_submitted_or_inprogress(user)

    def all_drafts(self, user):
        qs = self.get_queryset().filter(visible_to_students=False)

        if user.is_staff:
            return qs
        else:  # TA
            return qs.editable(user)


class Quest(IsAPrereqMixin, HasPrereqsMixin, TagsModelMixin, XPItem):
    verification_required = models.BooleanField(default=True,
                                                help_text="Teacher must approve submissions of this quest.  If \
                                                unchecked then submissions will automatically be approved and XP \
                                                granted without the teacher seeing the submission.")
    hideable = models.BooleanField(default=True, help_text="Students can choose to hide this quest from their list of \
                                                 available quests. ")
    available_outside_course = models.BooleanField(default=False,
                                                   help_text="Allows student to view and submit this quest without "
                                                             "having joined a course.  E.g. for quests you might "
                                                             "still want available to past students.")
    # categories = models.ManyToManyField(Category, blank=True)
    specific_teacher_to_notify = models.ForeignKey(
        settings.AUTH_USER_MODEL, limit_choices_to={'is_staff': True}, blank=True, null=True,
        help_text="Notifications related to this quest will be sent to this teacher "
                  "even if they do not teach the student.",
        on_delete=models.SET_NULL
    )
    campaign = models.ForeignKey(Category, blank=True, null=True, on_delete=models.SET_NULL)
    common_data = models.ForeignKey(CommonData, blank=True, null=True, on_delete=models.SET_NULL)
    instructions = models.TextField(blank=True, verbose_name='Quest Details')
    submission_details = models.TextField(blank=True, verbose_name='Submission Instructions')
    instructor_notes = models.TextField(blank=True, null=True,
                                        help_text="This field is only visible to Staff. \
                                        Use it to place answer keys or other notes.")

    editor = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, related_name="quest_editor",
                               help_text='Provides a student TA access to work on the draft of this quest.',
                               on_delete=models.SET_NULL)

    import_id = models.UUIDField(blank=True, null=True, default=uuid.uuid4, unique=True,
                                 help_text="Only edit this if you want to link to a quest in another system so that "
                                           "when importing from that other system, it will update this quest. "
                                           "Otherwise do not edit this or it will break existing links!")

    blocking = models.BooleanField(default=False,
                                   help_text="When this quest becomes available, it will block all other "
                                             "non-blocking quests until this one is submitted.")

    map_transition = models.BooleanField(
        default=False,
        help_text='Break maps at this quest. This quest will link to a new map.'
    )

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

    # Python by default doesn't inherit inner classes. In this case, the default ordering provided in XPItem.Meta is
    # not inherited, therefore we are doing it here.
    class Meta(XPItem.Meta):
        pass

    @classmethod
    def get_model_name(cls):
        return f'{cls._meta.app_label}.{cls._meta.model_name}'

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        elif self.campaign and self.campaign.icon and hasattr(self.campaign.icon, 'url'):
            return self.campaign.icon.url
        else:
            return SiteConfig.get().get_default_icon_url()

    def is_repeat_available(self, user):
        "Assumes one submission has already been completed"
        latest_sub = QuestSubmission.objects.all_for_user_quest(user, self, False).latest('first_time_completed')
        time_of_last = latest_sub.first_time_completed

        # happens if submission hasn't been completed yet. i.e. still in progress.
        if not time_of_last:
            return False

        # # to handle cases before first_time_completed existed as a property
        # if not latest_dt:
        #     # then latest_sub could be wrong.  Need to get latest completed date
        #     latest_sub = self.all_for_user_quest(user, quest, False).latest('time_completed')
        #     latest_dt = latest_sub.time_completed

        # if haven't maxed out repeats

        if self.repeat_per_semester:
            # get all completed this semester
            qs = QuestSubmission.objects.all_completed(user=user).filter(quest=self)
            if qs.count() > self.max_repeats:
                return False
        elif latest_sub.ordinal > self.max_repeats and self.max_repeats != -1:
            return False

        # Haven't maxed out yet, so check times
        time_since_last = timezone.now() - time_of_last
        hours_since_last = time_since_last.total_seconds() // 3600
        # and the proper amount of time has passed
        if hours_since_last >= self.hours_between_repeats:
            return True
        else:
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

    def is_editable(self, user):
        if user.is_staff:
            return True
        else:
            return user == self.editor and not self.visible_to_students

    def expired(self):
        """Returns True if the quest has expired, False otherwise.
        See QuestQueryset.expired() for details.
        """
        # utilize existing code in QuestQuerySet method not_expired()
        return not Quest.objects.filter(id=self.id).not_expired().exists()


# QuestSubmission ###############################################

class QuestSubmissionQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user=user)

    def block_if_needed(self):
        """ If there are blocking quests, only return them.  Otherwise, return full qs """
        subs_with_blocking_quests = self.filter(quest__blocking=True)
        if subs_with_blocking_quests:
            return subs_with_blocking_quests
        else:
            return self

    def get_quest(self, quest):
        return self.filter(quest=quest)

    def approved(self):
        return self.filter(is_approved=True).order_by('-time_approved')

    def not_approved(self):
        return self.filter(is_approved=False)

    def completed(self, oldest_first=False):
        if oldest_first:
            return self.filter(is_completed=True)
        else:
            return self.filter(is_completed=True).order_by('-time_completed')

    def not_completed(self):
        return self.filter(is_completed=False).order_by('-time_completed')

    def has_completion_date(self):
        return self.filter(time_completed__isnull=False)

    def grant_xp(self):
        """Filter the queryset of submissions to only include those that are not skipped, i.e. filter for do_not_grant_xp=False."""
        return self.filter(do_not_grant_xp=False)

    def get_semester(self, semester):
        return self.filter(semester=semester)

    def get_not_semester(self, semester):
        return self.exclude(semester=semester)

    def get_completed_before(self, date):
        return self.filter(time_approved__lte=date)

    def for_teacher_only(self, teacher):
        """
        :param teacher: a User model
        :return: qs filtered for submissions of students in the current teacher's blocks
        """
        if teacher is None:
            return self
        else:
            # Why doesn't this work?!? it only works for some teachers? with or without pk
            # return self.filter(user__coursestudent__block__current_teacher=teacher).distinct()
            # pk_sub_list = [
            #     sub.pk for sub in self
            #     if teacher.pk in sub.user.profile.teachers() or sub.quest.specific_teacher_to_notify == teacher
            # ]

            pk_sub_list = [
                sub.pk for sub in self
                if (
                    teacher.pk in sub.user.profile.teachers() or
                    (sub.quest.specific_teacher_to_notify == teacher if sub.quest else False)  # will error if quest has been deleted
                )
            ]

            return self.filter(pk__in=pk_sub_list)

    def exclude_archived_quests(self):
        return self.exclude(quest__archived=True)

    def exclude_quests_not_visible_to_students(self):
        return self.exclude(quest__visible_to_students=False)


class QuestSubmissionManager(models.Manager):
    def get_queryset(self,
                     active_semester_only=False,
                     exclude_archived_quests=True,
                     exclude_quests_not_visible_to_students=True):

        qs = QuestSubmissionQuerySet(self.model, using=self._db)
        if active_semester_only:
            qs = qs.get_semester(SiteConfig.get().active_semester.pk)
        if exclude_archived_quests:
            qs = qs.exclude_archived_quests()
        if exclude_quests_not_visible_to_students:
            qs = qs.exclude_quests_not_visible_to_students()
        return qs.select_related('quest')

    def flagged(self, user):
        return self.get_queryset().filter(flagged_by=user)

    def all_approved(self, user=None, quest=None, up_to_date=None, active_semester_only=True):
        """
        Return a queryset of all approved submissions within the provided parameters.

        If user is None, then this is a staff member's view of all approved submissions.
        If quest is provided, then this is a staff member's view of all approved submissions for that quest.
        """
        qs = self.get_queryset(active_semester_only,
                               exclude_archived_quests=False,
                               exclude_quests_not_visible_to_students=False
                               ).approved()

        if user:
            qs = qs.get_user(user)

        if quest is not None:
            qs = qs.get_quest(quest)

        if up_to_date is not None:
            qs = qs.get_completed_before(up_to_date)

        return qs

    # i.e In Progress
    def all_not_completed(self, user=None, active_semester_only=True, blocking=False):
        """ Returns a queryset of all QuestSubmissions that are currently in progress.
        This could be quests a student has started, or ones they have completed but have been returned.

        Keyword Arguments:
            user {User} -- if not provided, then will include in progress quests for all students. (default: {None})
            active_semester_only {bool} -- (default: {True})
            blocking {bool} -- Whether or not to account for blokcing quests.  This is only used if a User is provided. (default: {False})
        """
        if user is None:
            return self.get_queryset(active_semester_only).not_completed()

        # only returned quests will have a time completed, placing them on top
        qs = self.get_queryset(active_semester_only).get_user(user).not_completed()
        if blocking:
            return qs.block_if_needed()
        else:
            return qs

    def all_completed_past(self, user):
        qs = self.get_queryset(exclude_archived_quests=False,
                               exclude_quests_not_visible_to_students=False).get_user(user).completed()
        return qs.get_not_semester(SiteConfig.get().active_semester.pk).order_by('is_approved', '-time_approved')

    def all_completed(self, user=None, active_semester_only=True):
        qs = self.get_queryset(active_semester_only=active_semester_only,
                               exclude_archived_quests=False,
                               exclude_quests_not_visible_to_students=False
                               )
        if user is None:
            qs = qs.completed()
        else:
            qs = qs.get_user(user).completed().order_by('is_approved', '-time_approved')

        return qs

    def all_awaiting_approval(self, user=None, teacher=None):
        if user is None:
            qs = self.get_queryset(True).not_approved().completed(SiteConfig.get().approve_oldest_first)\
                .for_teacher_only(teacher)
            return qs
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

    def last_submission(self, user, quest):
        qs = self.all_for_user_quest(user, quest, False).order_by('ordinal')

        return qs.last()

    def not_submitted_or_inprogress(self, user, quest):
        """
        :return: True if the quest has not been started, or if it has been completed already
        or if it is a repeatable quest past the repeat time
        """
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

        # Handle repeatable quests with past submissions

        return quest.is_repeat_available(user)

    def create_submission(self, user, quest):
        last_submission = self.last_submission(user, quest)

        if last_submission:
            ordinal = last_submission.ordinal + 1
        else:
            ordinal = 1

        new_submission = QuestSubmission(
            quest=quest,
            user=user,
            ordinal=ordinal,
            semester_id=SiteConfig.get().active_semester.pk,
        )
        new_submission.save()
        return new_submission

    def calculate_xp(self, user):
        """
        Return the number of XP earned by a student for all xp-granting quests that they have completed so far.
        """
        return self.calculate_xp_to_date(user=user, date=None)

    def calculate_xp_to_date(self, user, date):
        """
        Return the number of XP earned by a student for all xp-granting quests that they have completed, up to and including the specified date.
        """
        total_xp = 0

        # Get all of the user's XP granting submissions for the active semester
        submissions_qs = self.all_approved(user, up_to_date=date).grant_xp()
        # print("\nSubmission_qs: ", submissions_qs)

        # annotate with xp_earned, since xp could come from xp_requested on the submission, or from the quest's xp value
        # take the greater value (since custom entry have the quest.xp as a minimum)
        submissions_qs = submissions_qs.annotate(xp_earned=Greatest('quest__xp', 'xp_requested'))

        # sum the xp_earned to prevent going over the max_xp per quest
        submission_xps = submissions_qs.order_by().values('quest', 'quest__max_xp').annotate(xp_sum=Sum('xp_earned'))

        for submission_xp in submission_xps:

            if submission_xp['quest__max_xp'] == -1:  # no limit
                total_xp += submission_xp['xp_sum']
            else:
                # Prevent xp going over the maximum gainable xp
                total_xp += min(submission_xp['xp_sum'], submission_xp['quest__max_xp'] or 0)  # quest__max_xp is None if quest is deleted, so `or 0`

        return total_xp

    def user_last_submission_completed(self, user):
        qs = self.get_queryset(True).get_user(user).completed()
        if not qs:
            return None
        else:
            return qs.latest('time_completed')

    def remove_in_progress(self):
        # In Progress Quests
        qs = self.all_not_completed(active_semester_only=False)
        num_del = qs.delete()
        return num_del


class QuestSubmission(models.Model):
    quest = models.ForeignKey(Quest, on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="quest_submission_user", on_delete=models.CASCADE)
    ordinal = models.PositiveIntegerField(default=1,
                                          help_text='indicating submissions beyond the first for repeatable quests')
    is_completed = models.BooleanField(default=False)
    # `first_time_completed` so that repeatable quests can count time from the first submission attempt
    first_time_completed = models.DateTimeField(null=True, blank=True)
    time_completed = models.DateTimeField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    time_approved = models.DateTimeField(null=True, blank=True)
    time_returned = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated = models.DateTimeField(auto_now=True, auto_now_add=False)
    do_not_grant_xp = models.BooleanField(default=False, help_text='The student will not earn XP for this quest.')
    semester = models.ForeignKey('courses.Semester', on_delete=models.SET_NULL, null=True)
    flagged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   related_name="quest_submission_flagged_by",
                                   help_text="flagged by a teacher for follow up",
                                   on_delete=models.SET_NULL)
    draft_text = models.TextField(null=True, blank=True)
    xp_requested = models.PositiveIntegerField(
        default=0,
        help_text='The number of XP you are requesting for this submission.'
    )

    class Meta:
        ordering = ["time_approved", "time_completed"]

    objects = QuestSubmissionManager()

    def __str__(self):
        if self.ordinal > 1:
            ordinal_str = " (" + str(self.ordinal) + ")"
        else:
            ordinal_str = ""

        if self.quest:
            name = self.quest.name
        else:
            name = "[DELETED QUEST]"
        name += ordinal_str
        return name

    def quest_name(self):
        if self.quest:
            return self.quest.name
        else:
            return "[DELETED QUEST]"

    def get_absolute_url(self):
        return reverse('quests:submission', kwargs={'submission_id': self.id})

    def mark_completed(self, xp_requested=0):
        self.is_completed = True
        self.time_completed = timezone.now()
        # this is only set the first time, so it can be referenced to
        # when calculating repeatable quests
        if self.first_time_completed is None:
            self.first_time_completed = self.time_completed
        self.draft_text = None  # clear draft stuff
        self.xp_requested = xp_requested
        self.save()

    def mark_approved(self, transfer=False):
        self.is_completed = True  # might have been false if returned
        self.is_approved = True
        self.time_approved = timezone.now()
        self.do_not_grant_xp = transfer
        self.save()
        # update badges
        BadgeAssertion.objects.check_for_new_assertions(self.user, transfer=transfer)
        self.user.profile.xp_invalidate_cache()  # recalculate XP

    def mark_returned(self):
        self.is_completed = False
        self.is_approved = False
        self.do_not_grant_xp = False
        self.time_returned = timezone.now()
        self.save()
        self.user.profile.xp_invalidate_cache()  # recalculate XP

    def is_awaiting_approval(self):
        return self.is_completed and not self.is_approved

    def is_returned(self):
        return self.time_completed is not None and not self.is_completed

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)

    def _fix_ordinal(self):
        # NOTE: There is a rare bug that we are unable to reproduce as of the moment where a QuestSubmission has the same ordinal.
        # This is just a temporary hack where it will automatically fix the incorrect ordinal
        # See issue for context: https://github.com/bytedeck/bytedeck/issues/1260
        broken_ordinal_start = self.ordinal - 1
        submissions = QuestSubmission.objects.filter(quest=self.quest, user=self.user, ordinal__gte=self.ordinal - 1).order_by('time_completed')

        for submission in submissions:
            submission.ordinal = broken_ordinal_start
            submission.save()

            broken_ordinal_start += 1

    def get_previous(self):
        """ If this is a repeatable quest and has been completed already, return that previous submission """

        if self.ordinal is None or self.ordinal <= 1:
            return None

        try:
            return QuestSubmission.objects.get(quest=self.quest, user=self.user, ordinal=self.ordinal - 1)
        except QuestSubmission.MultipleObjectsReturned:
            self._fix_ordinal()

        # Attempt to fetch to previoius after the ordinals are fixed
        self.refresh_from_db()
        return self.get_previous()

    def get_minutes_to_complete(self):
        """Returns the difference in minutes between first_time_complete and the (creation) timestamp.
        If the submission was returned then return None.
        """
        if not self.first_time_completed:
            return None

        minutes = (self.first_time_completed - self.timestamp).total_seconds() / 60
        return minutes
