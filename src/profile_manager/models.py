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
from courses.models import Rank, CourseStudent

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
    alias = models.CharField(max_length=50, unique=True, null=True, blank=True, default=None)
    first_name = models.CharField(max_length=50, null=True, blank=False)
    last_name = models.CharField(max_length=50, null=True, blank=False)
    preferred_name = models.CharField(max_length=50, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    student_number = models.PositiveIntegerField(unique=True, blank=False, null=True)
    grad_year = models.PositiveIntegerField(choices=get_grad_year_choices(), null=True, blank=False)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    intro_tour_completed = models.BooleanField(default = False)
    game_lab_transfer_process_on = models.BooleanField(default = False)
    banned_from_comments = models.BooleanField(default = False)

    objects = ProfileManager()

    def __str__(self):
        profile = ""
        if self.first_name:
            profile = self.first_name
            if self.preferred_name:
                profile += " (" + self.preferred_name + ")"
            profile += " " + self.last_name
            if self.alias:
                profile += ", aka " + self.alias
        else:
            profile = self.user.username
        return profile

    class Meta:
        ordering = ['user__username']

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
        xp = QuestSubmission.objects.calculate_xp(self.user)
        xp += BadgeAssertion.objects.calculate_xp(self.user)
        xp += CourseStudent.objects.calculate_xp(self.user)
        return xp

    def mark(self):
        course = CourseStudent.objects.current_course(self.user)
        if course:
            return course.calc_mark(self.xp())
        else:
            return None

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
        try:
            return self.xp() - self.rank().xp
        except:
            return 0

def create_profile(sender, **kwargs):
    current_user = kwargs["instance"]
    if kwargs["created"]:
        new_profile = Profile(user=current_user)
        new_profile.save()

        notify.send(
            current_user,
            recipient=User.objects.filter(is_staff=True).first(), #admin user
            affected_users=User.objects.filter(is_staff=True),
            icon="<i class='fa fa-fw fa-lg fa-user'></i>",
            verb='new user created')

post_save.connect(create_profile, sender=User)
