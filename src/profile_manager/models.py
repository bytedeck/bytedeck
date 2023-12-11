# import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.validators import validate_comma_separated_integer_list
from django.db import models
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from django_resized import ResizedImageField
from django_tenants.utils import get_public_schema_name

from badges.models import BadgeAssertion
from courses.models import CourseStudent, Rank
from notifications.signals import notify
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig
from utilities.models import RestrictedFileField

from allauth.account.signals import email_confirmed, user_logged_in, email_confirmation_sent, user_logged_out
from allauth.account.models import EmailAddress, EmailConfirmationHMAC


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

    def get_active(self):
        return self.filter(user__is_active=True)

    def get_inactive(self):
        return self.filter(user__is_active=False)


class ProfileManager(models.Manager):
    def get_queryset(self):
        return ProfileQuerySet(self.model, using=self._db).select_related('user')

    def all_students(self):
        return self.get_queryset().students_only()

    def all_for_active_semester(self):
        """:return: a queryset of student profiles with a course this semester"""
        courses_user_list = CourseStudent.objects.all_users_for_active_semester()
        qs = self.all_students().filter(user__in=courses_user_list, user__is_active=True)
        return qs

    def get_mailing_list(
        self,
        as_emails_list=False,
        for_announcement_email=False,
        for_notification_email=False,
    ):
        """
        :param as_emails_list: If True, return a list of emails instead of a queryset of users
        :param for_announcement_email: If True, only return users who want announcements by email
        :param for_notification_email: If True, only return users who want notifications by email
        """

        email_filter = models.Q()

        if for_announcement_email:
            email_filter &= models.Q(profile__get_announcements_by_email=True)

        if for_notification_email:
            email_filter &= models.Q(profile__get_notifications_by_email=True)

        empty_emails = models.Q(email='') | models.Q(email__isnull=True)
        verified_emails = models.Q(emailaddress__verified=True, emailaddress__primary=True)

        students_to_email = (
            CourseStudent.objects.all_users_for_active_semester()
                                 .filter(verified_emails)
                                 .exclude(empty_emails)
                                 .filter(email_filter)
        )

        teachers_to_email = (
            User.objects.filter(is_staff=True)
                        .filter(verified_emails)
                        .exclude(empty_emails)
                        .filter(email_filter)
        )

        # Merge the two querysets and remove duplicates
        users_to_email = (students_to_email | teachers_to_email).distinct()
        if as_emails_list:
            return list(users_to_email.values_list('email', flat=True))

        return users_to_email

    def all_visible(self):
        return self.get_queryset().visible()

    def all_active(self):
        return self.get_queryset().get_active()

    def all_inactive(self):
        return self.get_queryset().get_inactive()


def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/<use_id>/<filename>
    return f'{instance.user.username}/customstyles/{filename}'


class Profile(models.Model):
    # student_number_regex_string = r"^(9[89])(\d{5})$"
    # student_number_validator = RegexValidator(regex=student_number_regex_string,
    #                                           message="Invalid student number.",
    #                                           code='invalid_student_number',)

    @staticmethod
    def get_grad_year_choices():
        grad_year_choices = []
        for year in range(timezone.now().year, timezone.now().year + 5):
            grad_year_choices.append((year, year))  # (actual value, human readable name) tuples
        return grad_year_choices

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    alias = models.CharField(max_length=50, unique=False, null=True, blank=True, default=None,
                             help_text='You can leave this blank, or enter anything you like here.')
    avatar = ResizedImageField(upload_to='avatars/', null=True, blank=True)
    first_name = models.CharField(max_length=50, null=True, blank=False,
                                  help_text='Use the first name that matches your school records.')
    last_name = models.CharField(max_length=50, null=True, blank=False,
                                 help_text='Use the last name that matches your school records.')
    preferred_name = models.CharField(max_length=50, null=True, blank=True,
                                      verbose_name='Preferred first name',
                                      help_text='If you would prefer your teacher to call you by a name other than \
                                      the name on your school records, please put it here.')
    # student_number = models.PositiveIntegerField(unique=True, blank=False, null=True,
    #                                              validators=[student_number_validator])
    grad_year = models.PositiveIntegerField(null=True, blank=False)
    is_test_account = models.BooleanField(default=False,
                                          help_text="A test account that won't show up in student lists",
                                          )
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    intro_tour_completed = models.BooleanField(default=False)
    not_earning_xp = models.BooleanField(default=False)
    banned_from_comments = models.BooleanField(default=False)

    # Student options
    get_announcements_by_email = models.BooleanField(
        default=False,
        help_text="If you provided an email address on your profile, you will get announcements emailed to you when they are published."  # noqa
    )
    get_notifications_by_email = models.BooleanField(
        default=False,
        help_text="If you provided an email address on your profile, you will get unread notifications emailed to you once per day."  # noqa
    )
    get_messages_by_email = models.BooleanField(
        default=True,
        help_text="If your teacher sends you a message, get an instance email."  # noqa
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
                                            help_text='ADVANCED: A CSS file to customize this site!  You can use  \
                                                   this to tweak something, or create a completely new theme.')

    # Fields for caching data
    time_of_last_submission = models.DateTimeField(null=True, blank=True)
    xp_cached = models.IntegerField(default=0)
    mark_cached = models.DecimalField(max_digits=4, decimal_places=1, default=None, null=True, blank=True)

    objects = ProfileManager()

    #################################
    #
    #   "Get Name" methods
    #
    #################################

    def __str__(self):
        if self.user.first_name:
            profile = self.user.first_name
            if self.preferred_name:
                profile += " (" + self.preferred_name + ")"
            profile += " " + self.user.last_name
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
        elif self.user.first_name:
            return self.user.first_name
        else:
            return ""

    def alias_clipped(self):
        if self.alias is None:
            return "-"
        return self.alias if len(self.alias) < 15 else self.alias[:13] + "..."

    def preferred_full_name(self):
        name = self.get_preferred_name()
        if self.user.last_name:
            name += " " + self.user.last_name
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
        return self.user.get_full_name()

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

    def num_hidden_quests(self, available_only=True):
        """Returns the number of quests a student has placed in their hidden quest list.
        If available_only is True, then it will not count quests that the student wouldn't be able to see normally
        in there available quests list
        """
        hidden_quest_ids = self.get_hidden_quests_as_list()
        # convert list of ids as strings to integers so we can use intersection with the conditions_met list
        hidden_quest_ids = map(int, hidden_quest_ids)
        if available_only:
            # remove hidden otherwise there will be nothing left to intersect wtih
            available_quest_ids = Quest.objects.get_available(self.user, remove_hidden=False).values_list('id', flat=True)
            # only include quests ids that are in both lists
            hidden_quest_ids = set(available_quest_ids).intersection(hidden_quest_ids)

        return len(hidden_quest_ids)

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
            return current_courses.values_list('block__name', flat=True)
        else:
            return None

    # TODO: Is this used anywhere?  Seems to return the wrong data.  Also, duplicates current_teachers() method
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
        self.mark_cached = self.mark()
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
        courses = self.current_courses()
        cap_at_100 = SiteConfig.get().cap_marks_at_100_percent
        if courses:
            mark = courses[0].calc_mark(self.xp_cached) / len(courses)
            if cap_at_100:
                return min(mark, 100)
            else:
                return mark
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
        except:  # noqa
            # TODO
            return 0

    #################################
    #
    #   Miscellaneous
    #
    #################################

    def gone_stale(self):
        """ Return True if the user has not submitted a quest in the last 5 days"""
        if self.time_of_last_submission is None:
            return True
        else:
            return self.time_of_last_submission < timezone.now() - timezone.timedelta(days=5)

    def current_teachers(self):
        user_id_list = CourseStudent.objects.get_current_teacher_list(self.user)
        return User.objects.filter(id__in=user_id_list)


@receiver(post_save, sender=User)
def create_profile(sender, **kwargs):
    from django.db import connection

    if connection.schema_name != get_public_schema_name():
        current_user = kwargs["instance"]

        if kwargs["created"]:
            new_profile = Profile(user=current_user)

            new_profile.save()

            staff_list = User.objects.filter(is_staff=True)
            notify.send(
                current_user,
                target=new_profile,
                recipient=staff_list[0],
                affected_users=staff_list,
                icon="<i class='fa fa-fw fa-lg fa-user text-success'></i>",
                verb='.  New user registered: ')


@receiver(post_delete, sender=Profile)
def post_delete_user(sender, instance, *args, **kwargs):
    """If a profile is deleted, then that to cascade and delete profile as well.
    """
    if instance.user:  # just in case user is not specified or was already deleted
        instance.user.delete()


@receiver(email_confirmed, sender=EmailConfirmationHMAC)
def email_confirmed_handler(email_address, **kwargs):
    """
    django-allauth has their own model for tracking email address under `allauth.account.models.EmailAddress`

    Every time a user updates their email address under the Profile page, we send a confirmation email in the
    `profile_manager.ProfileForm.save()` method via `allauth.account.utils.send_email_confirmation`.

    and everytime that function is called, it creates a new EmailAddress record which with verified=False and primary=False
    as the attributes.

    Whenever they confirm an email address via the link sent to their email, this receiver gets called when that email
    is confirmed and we make that email the primary email address.

    The old EmailAddress record becomes primary=False and will be deleted so that we always only have one record
    under EmailAddress for a user.

    """

    with transaction.atomic():
        email_address.set_as_primary()

        # Delete all email addresses that are not primary and exclude emails used for social login
        user = email_address.user
        emails_qs = user.emailaddress_set.filter(primary=False)

        # Exclude email addresses used for logging in with social providers like google
        # We can't query it like user.socialaccount_set.values_list(extra_data__email, flat=True)
        # because django-allauth uses a different implementation of JSONField.
        # See: https://github.com/pennersr/django-allauth/issues/2599
        social_emails = []
        for data in user.socialaccount_set.values_list("extra_data", flat=True):
            email = data.get("email")
            if email:
                social_emails.append(email)

        if social_emails:
            emails_qs = emails_qs.exclude(email__in=social_emails)

        emails_qs.delete()


@receiver(email_confirmation_sent, sender=EmailConfirmationHMAC)
def email_confirmation_sent_recently_signed_up_with_email(request, signup, **kwargs):
    if not signup:
        return

    # Add an attribute to request that an email confirmation as been already sent
    request.recently_signed_up_with_email = True


@receiver(user_logged_out, sender=User)
def user_logged_out_handler(request, user, **kwargs):
    if hasattr(request, 'recently_signed_up_with_email'):
        del request.recently_signed_up_with_email


@receiver(user_logged_in, sender=User)
def user_logged_in_verify_email_reminder_handler(request, user, **kwargs):
    """
    Adds a django message to remind user to verify their email upon login
    """

    email_address = EmailAddress.objects.filter(email=user.email).first()

    recently_signed_up_with_email = getattr(request, 'recently_signed_up_with_email', False)

    # Only send the email when they login again
    if not recently_signed_up_with_email:
        if email_address and email_address.verified is False:
            messages.info(request, f"Please verify your email address: {user.email}.")


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

    if value in ["", "[]", "[ ]", None]:
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
        raise ValueError(f"Unable to parse value '{value}': {ex}")
