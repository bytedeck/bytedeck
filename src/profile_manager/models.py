from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.templatetags.static import static

from notifications.signals import notify

from datetime import datetime

from djconfig import config

from quest_manager.models import QuestSubmission
from badges.models import BadgeAssertion
from courses.models import Rank, CourseStudent

GRAD_YEAR_CHOICES = []
for r in range(datetime.now().year, datetime.now().year+4):
        GRAD_YEAR_CHOICES.append((r,r)) #(actual value, human readable name) tuples

class ProfileQuerySet(models.query.QuerySet):
    def get_grad_year(self, year):
        return self.filter(grad_year = year)

    def announcement_email(self):
        return self.filter(get_announcements_by_email = True)

    def visible(self):
        return self.filter(visible_to_other_students = True)

    def get_semester(self, semester):
        return self.filter(active_in_current_semester = semester)

class ProfileManager(models.Manager):
    def get_queryset(self):
        qs = ProfileQuerySet(self.model, using=self._db)
        if config.hs_view_active_semester_only:
            qs = qs.get_semester(config.hs_active_semester)
        return qs

    def get_mailing_list(self):
        return self.get_queryset().announcement_email()

    def all_visible(self):
        return self.get_queryset().visible()

class Profile(models.Model):

    def get_grad_year_choices():
        grad_year_choices = []
        for r in range(datetime.now().year, datetime.now().year+4):
                grad_year_choices.append((r,r)) #(actual value, human readable name) tuples
        return grad_year_choices

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=False)
    alias = models.CharField(max_length=50, unique=False, null=True, blank=True, default=None)
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
    get_announcements_by_email = models.BooleanField(default = False)
    visible_to_other_students = models.BooleanField(default = False)
    # New students automatically active,
    # all existing students should be changed to "inactive" at the end of the semester
    # they should be reactivated when they join a new course in a new (active) semester
    active_in_current_semester = models.BooleanField(default = True)

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

    def has_past_courses(self):
        semester = config.hs_active_semester
        past_courses = CourseStudent.objects.all_for_user_not_semester(self.user, semester)
        if past_courses:
            return True
        else:
            return False

    def has_current_course(self):
        current_courses = CourseStudent.objects.current_courses(self.user)
        if current_courses:
            return True
        else:
            return False


    def xp(self):
        xp = QuestSubmission.objects.calculate_xp(self.user)
        xp += BadgeAssertion.objects.calculate_xp(self.user)
        xp += CourseStudent.objects.calculate_xp(self.user)
        return xp

    def xp_per_course(self):
        return self.xp()/self.num_courses()

    def num_courses(self):
        return CourseStudent.objects.all_for_user(self.user).count()

    def mark(self):
        course = CourseStudent.objects.current_course(self.user)
        courses = CourseStudent.objects.all_for_user(self.user)
        if courses and course:
            return course.calc_mark(self.xp())/courses.count()
        else:
            return None

    def chillax(self):
        course = CourseStudent.objects.current_course(self.user)
        if course:
            semester = course.semester
            if semester and semester.chillax_line_started():
                return int(self.xp_per_course()) >= int(semester.chillax_line())
        return False


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

    def last_submission_completed(self):
        return QuestSubmission.objects.user_last_submission_completed(self.user)

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
