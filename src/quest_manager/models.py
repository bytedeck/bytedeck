from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q, Max
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

# from django.contrib.contenttypes.models import ContentType
# from django.contrib.contenttypes import generic

from datetime import time, date
from django.utils import timezone

from comments.models import Comment



class Course(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True,blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class Category(models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    active = models.BooleanField(default=True)
    course = models.ForeignKey(Course, null=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.title



class XPItem(models.Model):
    name = models.CharField(max_length=50, unique=True)
    xp = models.PositiveIntegerField(default = 0)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    tags = GenericRelation("TaggedItem", null=True, blank=True)
    # creator = models.CharField(max_length=250)
    # last_editor = models.CharField(max_length=250)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    visible_to_students = models.BooleanField(default = True)
    max_repeats = models.IntegerField(default = 0, help_text = '0 = not repeatable, enter -1 for unlimited')
    hours_between_repeats = models.PositiveIntegerField(default = 0)
    date_available = models.DateField(default=timezone.now)
    time_available = models.TimeField(default=time().min) # midnight
    date_expired = models.DateField(blank=True, null=True)
    time_expired = models.TimeField(blank=True, null=True)
    minimum_XP = models.PositiveIntegerField(blank=True, null=True)
    maximum_XP = models.PositiveIntegerField(blank=True, null=True)
    # prerequisites = generic.GenericRelation(Prerequisite)
    # prerequisites_advanced = models.CharField(max_length=250)
    icon = models.ImageField(upload_to='icons/', blank=True, null=True) #needs Pillow for ImageField

    class Meta:
        abstract = True

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

    def not_expired(self):
        return self.filter( Q(date_expired = None) | Q(date_expired__gt = timezone.now) )

    def visible(self):
        return self.filter(visible_to_students = True)

class QuestManager(models.Manager):
    def get_queryset(self):
        return QuestQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().date_available().not_expired().visible()

    def get_available(self, user):
        qs = self.get_active()
        quest_list = list(qs)
        # http://stackoverflow.com/questions/1207406/remove-items-from-a-list-while-iterating-in-python
        available_quests = [q for q in quest_list if QuestSubmission.objects.quest_is_available(user, q)]
        return available_quests


class Quest(XPItem):
    verification_required = models.BooleanField(default = True, )
    categories = models.ManyToManyField(Category, blank=True)
    instructions = models.TextField(blank=True)
    submission_details = models.TextField(blank=True)

    objects = QuestManager()

    def is_repeat_available(self, time_of_last, ordinal_of_last):
        # if haven't maxed out repeats
        if self.max_repeats == -1 or self.max_repeats >= ordinal_of_last:
            time_since_last = timezone.now() - time_of_last
            hours_since_last = time_since_last.total_seconds()//3600
            # and the proper amount of time has passed
            if hours_since_last > self.hours_between_repeats:
                return True
        return False

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

class Prerequisite(models.Model):
    parent_quest = models.ForeignKey(Quest)
    # Generic relations:
    # https://docs.djangoproject.com/en/1.4/ref/contrib/contenttypes/#generic-relations
    # content_type = models.ForeignKey(ContentType)
    # object_id = models.PositiveIntegerField()
    # content_object = generic.GenericForeignKey('content_type', 'object_id')
    prerequisite_item = models.ForeignKey(Quest, related_name='prerequisite_item')
    invert_prerequisite = models.BooleanField(help_text = 'item is available if user does NOT have this pre-requisite')
    alternate_prerequisite_item_1 = models.ForeignKey(Quest, related_name='alternate_prerequisite_item_1',
        help_text = 'user must have one of the prerequisite items',  blank=True, null=True)
    invert_alt_prerequisite_1 = models.BooleanField(help_text = 'item is available if user does NOT have this pre-requisite')
    alternate_prerequisite_item_2 = models.ForeignKey(Quest, related_name='alternate_prerequisite_item_2',
        help_text = 'user must have one of the prerequisite items', blank=True, null=True)
    invert_alt_prerequisite_2 = models.BooleanField(help_text = 'item is available if user does NOT have this pre-requisite')
    # minimum_rank =
    # maximum_rank =

    # def __str__(self):
    #     return self.category
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
        return self.filter(is_completed=True)

    def not_completed(self):
        return self.filter(is_completed=False)

    def has_completion_date(self):
        return self.filter(time_completed__isnull=False)

class QuestSubmissionManager(models.Manager):
    def get_queryset(self):
        return QuestSubmissionQuerySet(self.model, using=self._db)

    def all_not_approved(self, user=None):
        if user is None:
            return self.get_queryset().not_approved()
        return self.get_queryset().get_user(user).not_approved()

    def all_approved(self, user=None):
        if user is None:
            return self.get_queryset().approved().completed()
        return self.get_queryset().get_user(user).approved().completed()

    def all_not_completed(self, user=None):
        if user is None:
            return self.get_queryset().not_completed()
        return self.get_queryset().get_user(user).not_completed()

    def all_completed(self, user=None):
        if user is None:
            return self.get_queryset().completed()
        return self.get_queryset().get_user(user).completed()

    def all_awaiting_approval(self, user=None):
        if user is None:
            return self.get_queryset().not_approved().completed()
        return self.get_queryset().get_user(user).not_approved().completed()

    def all_returned(self, user=None):
        #completion date indicates the quest was submitted, but since completed
        #is false, it must have been returned.
        if user is None:
            return self.get_queryset().not_completed().has_completion_date()
        return self.get_queryset().get_user(user).not_completed().has_completion_date()

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
        else:
            latest_sub = self.all_for_user_quest(user, quest).latest('time_completed')
            latest_dt = latest_sub.time_completed
            if latest_dt is None: # quest submission in progress already
                return False
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

class QuestSubmission(models.Model):
    quest = models.ForeignKey(Quest)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="quest_submission_user")
    ordinal = models.PositiveIntegerField(default = 1, help_text = 'indicating submissions beyond the first for repeatable quests')
    is_completed = models.BooleanField(default=False)
    time_completed = models.DateTimeField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    time_approved = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True, auto_now_add=False)
    updated = models.DateTimeField(auto_now=False, auto_now_add=True)
    # rewards =

    objects = QuestSubmissionManager()

    def __str__(self):
        return self.user.get_username() + "-" + self.quest.name + "-" + str(self.ordinal)

    def get_absolute_url(self):
        return reverse('quests:submission', kwargs={'submission_id': self.id})

    def mark_completed(self):
        self.is_completed = True
        self.time_completed = timezone.now()
        self.save()

    def mark_approved(self):
        self.is_approved = True
        self.time_approved = timezone.now()
        self.save()

    def mark_returned(self):
        self.is_complete = False
        self.save()

    def is_awaiting_approval(self):
        return is_completed and not is_approved

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)
