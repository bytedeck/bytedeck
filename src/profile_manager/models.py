from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.templatetags.static import static

from notifications.signals import notify

from datetime import datetime

from quest_manager.models import QuestSubmission
from badges.models import BadgeAssertion
from courses.models import Rank

GRAD_YEAR_CHOICES = []
for r in range(datetime.now().year, datetime.now().year+4):
        GRAD_YEAR_CHOICES.append((r,r)) #(actual value, human readable name) tuples

class ProfileQuerySet(models.query.QuerySet):
    def get_grad_year(self, year):
        return self.filter(grad_year = year)

class ProfileManager(models.Manager):
    def get_queryset(self):
        return ProfileQuerySet(self.model, using=self._db)

class Profile(models.Model):

    def get_grad_year_choices():
        grad_year_choices = []
        for r in range(datetime.now().year, datetime.now().year+4):
                grad_year_choices.append((r,r)) #(actual value, human readable name) tuples
        return grad_year_choices

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=False)
    alias = models.CharField(max_length=50, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, null=True, blank=False)
    last_name = models.CharField(max_length=50, null=True, blank=False)
    preferred_name = models.CharField(max_length=50, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    student_number = models.PositiveIntegerField(unique=True, blank=False, null=True)
    grad_year = models.PositiveIntegerField(choices=get_grad_year_choices(), null=True, blank=False)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    intro_tour_completed = models.BooleanField(default = False)

    objects = ProfileManager()

    def __str__(self):
        return self.user.get_username()

    def get_absolute_url(self):
        return reverse('profiles:profile_detail', kwargs={'pk':self.id})
        # return reverse('profiles:profile_detail', kwargs={'pk':self.id})
        #return u'/some_url/%d' % self.id

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        else:
            return static('img/default_avatar.jpg')

    def xp(self):
        return QuestSubmission.objects.calculate_xp(self.user) + BadgeAssertion.objects.calculate_xp(self.user)

    def rank(self):
        return Rank.objects.get_rank(self.xp())

    def next_rank(self):
        return Rank.objects.get_next_rank(self.xp())

    def xp_to_next_rank(self):
        next_rank = self.next_rank()
        if next_rank == None:
            return 0 #maxed out!
        return self.next_rank().xp - self.rank().xp

    def xp_since_last_rank(self):

        return self.xp() - self.rank().xp

def create_profile(sender, **kwargs):
    current_user = kwargs["instance"]
    if kwargs["created"]:
        new_profile = Profile(user=current_user)
        new_profile.save()

        notify.send(
            current_user,
            recipient=User.objects.get(username='90158'), #admin user
            verb='new user created')

post_save.connect(create_profile, sender=User)
