from courses.models import Semester
from django.conf import settings
from django.urls import reverse
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Create your models here.
from comments.models import Comment


class SuggestionQuerySet(models.query.QuerySet):
    def all_user(self, user):
        return self.filter(user=user)

    def awaiting_approval(self):
        return self.filter(status=Suggestion.AWAITING_APPROVAL)

    def awaiting_approval_for_user(self, user):
        return self.exclude(status=Suggestion.AWAITING_APPROVAL, user=user)

    def approved(self):
        return self.filter(status=Suggestion.APPROVED)

    def completed(self):
        return self.filter(status=Suggestion.COMPLETED)

    def not_approved(self):
        return self.filter(status=Suggestion.NOT_AOPPROVED)

    def unlikely(self):
        return self.filter(status=Suggestion.UNLIKELY)


class SuggestionManager(models.Manager):
    def get_queryset(self):
        return SuggestionQuerySet(self.model, using=self._db)

    def all_for_students(self):
        return self.get_queryset().approved()

    def all_for_student(self, user):
        # all suggestions from the user, but only approved ones from others
        return self.get_queryset().filter(Q(status=Suggestion.APPROVED) | Q(user=user))

    def all_completed(self):
        return self.get_queryset().completed()

    def all_rejected(self):
        return self.get_queryset().not_approved()


class Suggestion(models.Model):
    AWAITING_APPROVED = 1
    APPROVED = 2
    COMPLETED = 3
    UNLIKELY = 4
    NOT_APPROVED = 5
    STATUSES = ((AWAITING_APPROVED, 'awaiting approval'),
                (APPROVED, 'approved'),
                (COMPLETED, 'completed'),
                (UNLIKELY, 'unlikely'),
                (NOT_APPROVED, 'not approved'),
                )

    title = models.CharField(max_length=50, help_text="Briefly describes the suggestion")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    description = models.TextField(
        help_text="A detailed explanation includes WHAT the suggestion is, \
        WHY the suggestions will improve the Hackerspace, \
        and HOW Mr C can implement the suggestion. ")
    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)
    status = models.PositiveIntegerField(choices=STATUSES, default=AWAITING_APPROVED)
    status_timestamp = models.DateTimeField(null=True, blank=True)
    objects = SuggestionManager()

    class Meta:
        ordering = ['status']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('suggestions:list', kwargs={'id': self.pk})

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)

    def get_score(self):
        return Vote.objects.get_score(self)


class VoteQuerySet(models.query.QuerySet):
    def all_user(self, user):
        return self.filter(user=user)

    def all_suggestion(self, suggestion):
        return self.filter(suggestion=suggestion)


class VoteManager(models.Manager):
    def get_queryset(self):
        return VoteQuerySet(self.model, using=self._db)

    def record_vote(self, suggestion, user, vote):
        """Need to check if user has voted yet today"""
        if vote > 0:
            vote = 1
        elif vote < 0:
            vote = -1

        if self.user_can_vote(user):
            new_vote = self.model(
                user=user,
                suggestion=suggestion,
                vote=vote,
            )
            new_vote.save(using=self._db)
            return new_vote
        else:
            return None

    def get_score(self, suggestion):
        qs = self.get_queryset().all_suggestion(suggestion).aggregate(models.Sum('vote'))
        # print("**********************GET SCORE *******************")
        # print(qs)
        if not qs['vote__sum']:
            return 0
        return qs['vote__sum']

    def user_can_vote(self, user):
        """Can vote once per day"""
        qs = self.get_queryset().all_user(user)
        if not qs:
            return True

        most_recent = qs.latest('timestamp')
        if most_recent.timestamp.date() < timezone.now().date():
            return True
        return False

    def all_this_semester(self, user):
        qs = self.get_queryset().all_user(user)
        sem = Semester.objects.get_current()
        return qs.filter(timestamp__date__range=(sem.first_day, sem.last_day))


class Vote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    suggestion = models.ForeignKey(Suggestion, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)
    vote = models.SmallIntegerField(help_text="up vote is +1, down vote is -1")

    objects = VoteManager()

    def __str__(self):
        return str(self.user) + " on " + str(self.timestamp.date())

    def is_upvote(self):
        return self.vote > 0

    def is_downvote(self):
        return self.vote < 0
