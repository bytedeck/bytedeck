import re

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, validate_comma_separated_integer_list
from django.db import models
from django.db.models.signals import post_save
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from siteconfig.models import SiteConfig
from django_tenants.utils import get_public_schema_name

from badges.models import BadgeAssertion
from courses.models import Rank, CourseStudent
from notifications.signals import notify
from quest_manager.models import QuestSubmission
from utilities.models import RestrictedFileField


class ProfileQuerySet(models.query.QuerySet):
    def get_grad_year(self, year):
        return self.filter(grad_year=year)

    def announcement_email(self):
        return self.filter(get_announcements_by_email=True)

    def visible(self):
        return self.filter(visible_to_other_students=True)

    def get_semester(self, semester):
        return self.filter(active_in_current_semester=semester)

    def students_only(self):
        return self.filter(user__is_staff=False, is_test_account=False)


class ProfileManager(models.Manager):
    def get_queryset(self):
        return ProfileQuerySet(self.model, using=self._db).select_related('user')

    def all_students(self):
        return self.get_queryset().students_only()

    def all_for_active_semester(self):
        """:return: a queryset of student profiles with a course this semester"""
        courses_user_list = CourseStudent.objects.all_users_for_active_semester()
        qs = self.all_students().filter(user__in=courses_user_list)
        return qs

    def get_mailing_list(self):
        return self.get_queryset().announcement_email()

    def all_visible(self):
        return self.get_queryset().visible()


def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/<use_id>/<filename>
    return '{0}/customstyles/{1}'.format(instance.user.username, filename)


class Profile(models.Model):
    student_number_regex_string = r"^(9[89])(\d{5})$"
    student_number_validator = RegexValidator(regex=student_number_regex_string,
                                              message="Invalid student number.",
                                              code='invalid_student_number',)

    @staticmethod
    def get_grad_year_choices():
        grad_year_choices = []
        for year in range(timezone.now().year, timezone.now().year + 5):
            grad_year_choices.append((year, year))  # (actual value, human readable name) tuples
        return grad_year_choices

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    alias = models.CharField(max_length=50, unique=False, null=True, blank=True, default=None,
                             help_text='You can leave this blank, or enter anything you like here.')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    first_name = models.CharField(max_length=50, null=True, blank=False,
                                  help_text='Use the first name that matches your school records.')
    last_name = models.CharField(max_length=50, null=True, blank=False,
                                 help_text='Use the last name that matches your school records.')
    preferred_name = models.CharField(max_length=50, null=True, blank=True,
                                      verbose_name='Preferred first name',
                                      help_text='If you would prefer your teacher to call you by a name other than \
                                      the name on your school records, please put it here.')
    student_number = models.PositiveIntegerField(unique=True, blank=False, null=True,
                                                 validators=[student_number_validator])
    grad_year = models.PositiveIntegerField(null=True, blank=False)
    is_test_account = models.BooleanField(default=False,
                                          help_text="A test account that won't show up in student lists",
                                          )
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    intro_tour_completed = models.BooleanField(default=False)
    game_lab_transfer_process_on = models.BooleanField(default=False)
    banned_from_comments = models.BooleanField(default=False)
    xp_cached = models.IntegerField(default=0)

    # Student options
    get_announcements_by_email = models.BooleanField(
        default=False,
        help_text="If you provided an email address on your profile, you will get announcements emailed to you when they are published." # noqa
    )
    get_notifications_by_email = models.BooleanField(
        default=False,
        help_text="If you provided an email address on your profile, you will get unread notifications emailed to you once per day." # noqa
    )
    get_messages_by_email = models.BooleanField(
        default=True,
        help_text="If your teacher sends you a message, get an instance email." # noqa
    )
    visible_to_other_students = models.BooleanField(
        default=False, help_text="Your marks will be visible to other students through the student list.")
    preferred_internal_only = models.BooleanField(
        verbose_name='Use preferred first name internally only',
        default=False, help_text="Check this if you want your preferred name used ONLY in the classroom, but NOT in other places such as on your report card.")  # noqa
    dark_theme = models.BooleanField(default=False)
    silent_mode = models.BooleanField(default=False, help_text="Don't play the gong sounds.")
    hidden_quests = models.CharField(validators=[validate_comma_separated_integer_list], max_length=1023,
                                     null=True, blank=True)  # list of quest IDs
    is_TA = models.BooleanField(default=False, help_text="TAs can create new quests for teacher approval.")

    custom_stylesheet = RestrictedFileField(null=True, blank=True, upload_to=user_directory_path,
                                            content_types=['text/css', 'text/plain'],
                                            max_upload_size=512000,
                                            help_text='ADVANCED: A CSS file to customize the Hackerspace.  You can use  \
                                                   this to tweak something, or create a completely new theme.')

    objects = ProfileManager()

    #################################
    #
    #   "Get Name" methods
    #
    #################################

    def __str__(self):
        profile = ""
        if self.first_name:
            profile = self.first_name
            if self.preferred_name:
                profile += " (" + self.preferred_name + ")"
            profile += " " + self.last_name
            if self.alias:
                profile += ", aka " + self.alias_clipped()
        else:
            profile = self.user.username
        return profile

    class Meta:
        ordering = ['user__username']

    def get_preferred_name(self):
        # new students won't have name info yet
        if self.preferred_name:
            return self.preferred_name
        elif self.first_name:
            return self.first_name
        else:
            return ""

    def alias_clipped(self):
        if self.alias is None:
            return "-"
        return self.alias if len(self.alias) < 15 else self.alias[:13] + "..."

    def preferred_full_name(self):
        name = self.get_preferred_name()
        if self.last_name:
            name += " " + self.last_name
        return name if name else str(self.user)

    def public_name(self):
        if self.preferred_internal_only:
            return self.formal_name()
        else:
            return self.preferred_full_name()

    def internal_name(self):
        name = self.preferred_full_name()
        if self.alias:
            name += ", aka " + self.alias_clipped()
        return name

    def formal_name(self):
        if self.first_name and self.last_name:
            return self.first_name + " " + self.last_name
        else:
            return ""

    def get_absolute_url(self):
        return reverse('profiles:profile_detail', kwargs={'pk': self.id})

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        else:
            return static('img/default_avatar.jpg')

    #################################
    #
    #   HIDDEN QUEST MANAGEMENT
    #
    #################################

    def num_hidden_quests(self):
        hidden_quest_list = self.get_hidden_quests_as_list()
        return len(hidden_quest_list)

    def is_quest_hidden(self, quest):
        hidden_quest_list = self.get_hidden_quests_as_list()
        if str(quest.id) in hidden_quest_list:
            return True
        else:
            return False

    def get_hidden_quests_as_list(self):
        if self.hidden_quests is None:
            return []
        else:
            return smart_list(self.hidden_quests)

    def save_hidden_quests_from_list(self, hidden_quest_list):
        hidden_quest_csv = ",".join(hidden_quest_list)
        self.hidden_quests = hidden_quest_csv
        self.save()

    def hide_quest(self, quest_id):
        hidden_quest_list = self.get_hidden_quests_as_list()
        if str(quest_id) not in hidden_quest_list:
            hidden_quest_list.append(str(quest_id))
            self.save_hidden_quests_from_list(hidden_quest_list)

    def unhide_quest(self, quest_id):
        hidden_quest_list = self.get_hidden_quests_as_list()
        if str(quest_id) in hidden_quest_list:
            hidden_quest_list.remove(str(quest_id))
            self.save_hidden_quests_from_list(hidden_quest_list)

    #################################
    #
    #   Courses and blocks
    #
    #################################

    def num_courses(self):
        return self.current_courses().count()

    def current_courses(self):
        return CourseStudent.objects.current_courses(self.user)

    @cached_property
    def has_past_courses(self):
        semester = SiteConfig.get().active_semester
        return CourseStudent.objects.all_for_user_not_semester(self.user, semester).exists()

    @cached_property
    def has_current_course(self):
        return self.current_courses().exists()

    def blocks(self):
        current_courses = self.current_courses()
        if current_courses:
            return current_courses.values_list('block__block', flat=True)
        else:
            return None

    def teachers(self):
        teachers = self.current_courses().values_list('block__current_teacher', flat=True)
        return teachers

    #################################
    #
    #   XP and Marks
    #
    #################################

    def xp_invalidate_cache(self):
        xp = QuestSubmission.objects.calculate_xp(self.user)
        xp += BadgeAssertion.objects.calculate_xp(self.user)
        xp += CourseStudent.objects.calculate_xp(self.user)
        self.xp_cached = xp
        self.save()
        return xp

    def xp_per_course(self):
        course_count = self.num_courses()
        if not course_count or course_count == 0:
            return 0
        return self.xp_cached / course_count

    def xp_to_date(self, date):
        # TODO: Combine this with other methods?
        xp = QuestSubmission.objects.calculate_xp_to_date(self.user, date)
        xp += BadgeAssertion.objects.calculate_xp_to_date(self.user, date)
        # TODO: Add manual adjustments to calculation
        xp += CourseStudent.objects.calculate_xp(self.user)
        return xp

    def mark(self):
        # course = CourseStudent.objects.current_course(self.user)
        courses = self.current_courses()
        if courses:
            return courses[0].calc_mark(self.xp_cached) / len(courses)
        else:
            return None

    def chillax(self):
        course = CourseStudent.objects.current_course(self.user)
        if course:
            semester = course.semester
            if semester and semester.chillax_line_started():
                return int(self.xp_per_course()) >= semester.chillax_line()
        return False

    #################################
    #
    #   Ranks
    #
    #################################

    def rank(self):
        return Rank.objects.get_rank(self.xp_cached)

    def next_rank(self):
        return Rank.objects.get_next_rank(self.xp_cached)

    def xp_to_next_rank(self):
        next_rank = self.next_rank()
        if next_rank is None:
            return 0  # maxed out!
        return self.next_rank().xp - self.rank().xp

    def xp_since_last_rank(self):
        # TODO: Fix this laziness
        try:
            return self.xp_cached - self.rank().xp
        except: # noqa
            # TODO
            return 0

    #################################
    #
    #   Miscellaneous
    #
    #################################

    def last_submission_completed(self):
        return QuestSubmission.objects.user_last_submission_completed(self.user)

    def gone_stale(self):
        last_sub = self.last_submission_completed()
        if last_sub is None:
            return True
        else:
            if last_sub.time_completed:
                return last_sub.time_completed < timezone.now() - timezone.timedelta(days=5)
            else:
                return True

    def current_teachers(self):
        user_id_list = CourseStudent.objects.get_current_teacher_list(self.user)
        return User.objects.filter(id__in=user_id_list)


def create_profile(sender, **kwargs):
    from django.db import connection

    if connection.schema_name != get_public_schema_name():
        current_user = kwargs["instance"]

        if kwargs["created"]:
            new_profile = Profile(user=current_user)

            # if user's name matches student number (e.g 9912345), set student number:
            pattern = re.compile(Profile.student_number_regex_string)
            if pattern.match(current_user.get_username()):
                new_profile.student_number = int(current_user.get_username())

            # set first and last name on the profile.  This should be removed and just use the first and last name
            # from the user model! But when first implemented, first and last name weren't included in the the sign up form.
            new_profile.first_name = current_user.first_name
            new_profile.last_name = current_user.last_name

            new_profile.save()

            staff_list = User.objects.filter(is_staff=True)
            notify.send(
                current_user,
                target=new_profile,
                recipient=staff_list[0],
                affected_users=staff_list,
                icon="<i class='fa fa-fw fa-lg fa-user text-success'></i>",
                verb='.  New user registered: ')


post_save.connect(create_profile, sender=User)


def smart_list(value, delimiter=",", func=None):
    """Convert a value to a list, if possible.
    http://tech.yunojuno.com/working-with-django-s-commaseparatedintegerfield

    Args:
        value: the value to be parsed. Ideally a string of comma separated
            values - e.g. "1,2,3,4", but could be a list, a tuple, ...

    Kwargs:
        delimiter: string, the delimiter used to split the value argument,
            if it's a string / unicode. Defaults to ','.
        func: a function applied to each individual element in the list
            once the value arg is split. e.g. lambda x: int(x) would return
            a list of integers. Defaults to None - in which case you just
            get the list.

    Returns: a list if one can be parsed out of the input value. If the
             value input is an empty string or None, returns an empty
             list. If the split or func parsing fails, raises a ValueError.

    This is mainly used for ensuring the CSV model fields are properly
    formatted. Use this function in the save() model method and post_init()
    model signal to ensure that you always get a list back from the field.

    """
    if value in ["", u"", "[]", u"[]", u"[ ]", None]:
        return []

    if isinstance(value, list):
        ls = value
    elif isinstance(value, tuple):
        ls = list(value)
    elif isinstance(value, str):
        # TODO: regex this.
        value = value.lstrip('[').rstrip(']').strip(' ')
        if len(value) == 0:
            return []
        else:
            ls = value.split(delimiter)
    elif isinstance(value, int):
        ls = [value]
    else:
        raise ValueError("Unparseable smart_list value: %s" % value)

    try:
        func = func or (lambda x: x)
        return [func(e) for e in ls]
    except Exception as ex:
        raise ValueError("Unable to parse value '%s': %s" % (value, ex))
