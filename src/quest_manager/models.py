from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist,  MultipleObjectsReturned
from django.db import models
from django.db.models import Q, Max, Sum
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.templatetags.static import static

# from django.contrib.contenttypes.models import ContentType
# from django.contrib.contenttypes import generic

from datetime import time, date, datetime
from django.utils import timezone

from prerequisites.models import Prereq
from badges.models import BadgeAssertion
from comments.models import Comment

class Category(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.title

class CommonData(models.Model):
    title = models.CharField(max_length=50, unique=True)
    instructions = models.TextField()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class XPItem(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default = 0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    # tags = GenericRelation("TaggedItem", null=True, blank=True)
    # creator = models.CharField(max_length=250)
    # last_editor = models.CharField(max_length=250)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    visible_to_students = models.BooleanField(default = True)
    sort_order = models.IntegerField(default = 0)
    max_repeats = models.IntegerField(default = 0, help_text = '0 = not repeatable, enter -1 for unlimited')
    hours_between_repeats = models.PositiveIntegerField(default = 0)
    date_available = models.DateField(default=timezone.now)
    time_available = models.TimeField(default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True, help_text= 'only used if date_expired is blank')
    # minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    # maximum_XP = models.PositiveIntegerField(blank=True, null=True)
    # prerequisites = generic.GenericRelation(Prerequisite)
    # prerequisites_advanced = models.CharField(max_length=250)
    icon = models.ImageField(upload_to='icons/', blank=True, null=True) #needs Pillow for ImageField

    class Meta:
        abstract = True
        ordering = ["-sort_order", "-time_expired", "-date_expired", "name"]

    def __str__(self):
        return self.name

    #allow us to handle iconless items.  Use with: <img src="{{ object.icon|default_if_none:'#' }}" />
    def icon_url(self):
        if(self.icon and hasattr(self.icon, 'url')):
            return self.icon.url

    def get_absolute_url(self):
        return reverse('quests:quest_detail', kwargs={'quest_id': self.id})

    # def get_icon_url(self):
    #     return "/images/s.jpg"

# Create your models here.
class QuestQuerySet(models.query.QuerySet):
    def date_available(self):
        return self.filter(date_available__lte = timezone.now)

    #doesn't worktime is UTC or something
    def not_expired(self):
        qs_date = self.filter( Q(date_expired = None) | Q(date_expired__gte = datetime.now) )
        qs_date = qs_date.exclude( Q(date_expired = datetime.now) & Q(time_expired__gt = datetime.now ))
        return qs_date.exclude( Q(date_expired = None) & Q(time_expired__lt = datetime.now) )

    def visible(self):
        return self.filter(visible_to_students = True)

    #this should be generic and placed in the prerequisites app
    # extend models.Model (e.g. PrereqModel) and prereq users should subclass it
    def get_conditions_met(self, user):
        pk_met_list = [
                obj.pk for obj in self
                if Prereq.objects.all_conditions_met(obj, user)
                ]
        return self.filter(pk__in = pk_met_list)

class QuestManager(models.Manager):
    def get_queryset(self):
        return QuestQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().date_available().not_expired().visible()

    def get_available(self, user):
        qs = self.get_active().get_conditions_met(user)
        quest_list = list(qs)
        # http://stackoverflow.com/questions/1207406/remove-items-from-a-list-while-iterating-in-python
        available_quests = [q for q in quest_list if QuestSubmission.objects.quest_is_available(user, q)]
        return available_quests

class Quest(XPItem):
    verification_required = models.BooleanField(default = True, )
    categories = models.ManyToManyField(Category, blank=True)
    common_data = models.ForeignKey(CommonData, blank=True, null=True)
    instructions = models.TextField(blank=True)
    submission_details = models.TextField(blank=True)
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

    def expired(self):
        if self.date_expired == None:
            if self.time_expired == None:
                return False
            return datetime.now().time() > self.time_expired

        return datetime.now().date() > self.date_expired

    def is_repeat_available(self, time_of_last, ordinal_of_last):
        # if haven't maxed out repeats
        if self.max_repeats == -1 or self.max_repeats >= ordinal_of_last:
            time_since_last = timezone.now() - time_of_last
            hours_since_last = time_since_last.total_seconds()//3600
            # and the proper amount of time has passed
            if hours_since_last >= self.hours_between_repeats:
                return True
        return False

    # to help with the prerequisite choices!
    @staticmethod
    def autocomplete_search_fields():
        return ("name__icontains",)

    # all models that want to act as a possible prerequisite need to have this method
    # Create a default in the PrereqModel(models.Model) class that uses a default:
    # prereq_met boolean field.  Use that or override the method like this
    def condition_met_as_prerequisite(self, user, num_required):
        num_approved = QuestSubmission.objects.all_for_user_quest(user, self).approved().count()
        # print("num_approved: " + str(num_approved) + "/" + str(num_required))
        return num_approved >= num_required



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
("python","python"),
("django","django"),
)


#Demo of ContentType foreign key.  Model not actually in use
class TaggedItem(models.Model):
    tag = models.SlugField(choices=TAG_CHOICES)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()

    def get_absolute_url(self):
        return reverse('profile_detail', kwargs={'pk': self.pk})

    content_object = GenericForeignKey()

    def __str__(self):
        return self.tag

##### QuestSubmission ###############################################

class QuestSubmissionQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user=user)

    def get_quest(self, quest):
        return self.filter(quest=quest)

    def approved(self):
        return self.filter(is_approved=True)

    def not_approved(self):
        return self.filter(is_approved=False)

    def completed(self):
        return self.filter(is_completed=True).order_by('-time_completed')

    def not_completed(self):
        return self.filter(is_completed=False).order_by('-time_completed')

    def has_completion_date(self):
        return self.filter(time_completed__isnull=False)

    def no_game_lab(self):
        return self.filter(game_lab_transfer = False)

    def game_lab(self):
        return self.filter(game_lab_transfer = True)

class QuestSubmissionManager(models.Manager):
    def get_queryset(self):
        qs = QuestSubmissionQuerySet(self.model, using=self._db)
        return qs.select_related('quest')

    def all_not_approved(self, user=None):
        if user is None:
            return self.get_queryset().not_approved()
        return self.get_queryset().get_user(user).not_approved()

    def all_approved(self, user=None):
        if user is None:
            return self.get_queryset().approved().completed().no_game_lab()
        return self.get_queryset().get_user(user).approved().completed()

    def all_gamelab(self, user=None):
        if user is None:
            return self.get_queryset().approved().completed().game_lab()
        return self.get_queryset().get_user(user).approved().completed()

    def all_not_completed(self, user=None):
        if user is None:
            return self.get_queryset().not_completed()
        #only returned quests will have a time compelted, placing them on top
        return self.get_queryset().get_user(user).not_completed()

    def all_completed(self, user=None):
        if user is None:
            return self.get_queryset().completed()
        return self.get_queryset().get_user(user).completed().order_by(
                    'is_approved', '-time_approved')

    def all_awaiting_approval(self, user=None):
        if user is None:
            return self.get_queryset().not_approved().completed().order_by('time_completed')
        return self.get_queryset().get_user(user).not_approved().completed()

    def all_returned(self, user=None):
        #completion date indicates the quest was submitted, but since completed
        #is false, it must have been returned.
        if user is None:
            return self.get_queryset().not_completed().has_completion_date().order_by('-time_returned')
        return self.get_queryset().get_user(user).not_completed().has_completion_date().order_by('-time_returned')

    def all_for_user_quest(self, user, quest):
        return self.get_queryset().get_user(user).get_quest(quest)

    def num_submissions(self, user, quest):
        qs = self.all_for_user_quest(user, quest)
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
            s = self.all_not_completed(user=user).get(quest=quest)
            #if no exception is thrown it means that an inprogress submission was found
            return False
        except MultipleObjectsReturned:
            return False # multiple found
        except ObjectDoesNotExist:
            pass #nothing found, continue

        latest_sub = self.all_for_user_quest(user, quest).latest('first_time_completed')
        latest_dt = latest_sub.first_time_completed

        # to handle cases before first_time_completed existed as a property
        if not latest_dt:
            latest_dt = latest_sub.time_completed
        return quest.is_repeat_available(latest_dt, num_subs)

    def create_submission(self, user, quest):
        if self.quest_is_available(user, quest):
            ordinal = self.num_submissions(user, quest) + 1
            new_submission = QuestSubmission(
                quest = quest,
                user = user,
                ordinal = ordinal,
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


class QuestSubmission(models.Model):
    quest = models.ForeignKey(Quest)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="quest_submission_user")
    ordinal = models.PositiveIntegerField(default = 1, help_text = 'indicating submissions beyond the first for repeatable quests')
    is_completed = models.BooleanField(default=False)
    first_time_completed = models.DateTimeField(null=True, blank=True)
    time_completed = models.DateTimeField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    time_approved = models.DateTimeField(null=True, blank=True)
    time_returned = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True, auto_now_add=False)
    updated = models.DateTimeField(auto_now=False, auto_now_add=True)
    game_lab_transfer = models.BooleanField(default = False, help_text = 'XP not counted')
    # rewards =

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
        if self.first_time_completed == None:
            self.first_time_completed = timezone.now()
        self.save()

    def mark_approved(self, transfer = False):
        self.is_completed = True #might have been false if returned
        self.is_approved = True
        self.time_approved = timezone.now()
        self.game_lab_transfer = transfer
        self.save()
        #update badges
        BadgeAssertion.objects.check_for_new_assertions(self.user, transfer=transfer)

    def mark_returned(self):
        self.is_completed = False
        self.is_approved = False
        self.game_lab_transfer = False
        self.time_returned = timezone.now()
        self.save()

    def is_awaiting_approval(self):
        return (self.is_completed and not self.is_approved)

    def is_returned(self):
        return (self.time_completed != None and not self.is_completed)

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)
