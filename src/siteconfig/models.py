from copy import copy
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.exceptions import MultipleObjectsReturned
from django.db import connection, models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.conf import settings

from django_tenants.utils import get_public_schema_name, schema_context
from redis import exceptions as redis_exceptions

from utilities.models import RestrictedFileField

User = get_user_model()


def get_default_deck_owner():
    """
        This is run once during site initialization

        Also need to initialize owner if none exists yet.
        (Since initialization.py loads after everything else)
    """

    # handle existing decks by getting an existing staff user that is NOT bytedeck_admin:
    admin_username = settings.TENANT_DEFAULT_ADMIN_USERNAME
    non_admin_staff_qs = User.objects.filter(is_staff=True).exclude(username=admin_username)

    if non_admin_staff_qs.exists():  # i.e. there are more staff than just the admin user
        return non_admin_staff_qs.first().pk  # return the first one (assumes sorted by pk, so should be the oldest one?)

    else:  # no other staff users available yet, so we'll have to create them
        deck_owner = User.objects.create(
            username=settings.TENANT_DEFAULT_OWNER_USERNAME,
            is_staff=True,
        )
        return deck_owner.pk


def get_superadmin():
    """ Is there a way to get this cleanly from the new tenants app? """
    try:
        # is this only needed for tests? If not then need a unique username probably, not this!
        username = 'bytedeck_ai'
        superadmin, created = User.objects.get_or_create(is_staff=True, defaults={'username': username})
    except MultipleObjectsReturned:
        superadmin = User.objects.filter(is_staff=True).order_by('id')[0]
    return superadmin.id


def get_active_semester():
    """ Need to initialize a semester if none exists yet. """
    from courses.models import Semester  # import here to prevent ciruclar imports
    try:
        # is this only needed for tests? If not then need a unique username probably, not this!
        semester, created = Semester.objects.get_or_create()
    except MultipleObjectsReturned:
        semester = Semester.objects.order_by('-first_day')[0]
    return semester.id


class SiteConfig(models.Model):
    """ This model is intended to be a singleton for each tenant.
        Access the model instance using the settings() class function.
    """

    site_name = models.CharField(
        verbose_name="Site Name, Full", default="My Byte Deck", max_length=50,
        help_text="This name will appear throughout the site, for example: Timberline's Digital Hackerspace."
    )

    site_name_short = models.CharField(
        verbose_name="Site Name, Short", default="Deck", max_length=20,
        help_text="Used when the full site name is too cumbersome, for example: Hackerspace."
    )

    access_code = models.CharField(
        verbose_name="Access Code", default="314159", max_length=128,
        help_text="Students will need this to sign up to your deck.  You can set it to any string of characters you like."
    )

    banner_image = models.ImageField(
        verbose_name="Banner Image", null=True, blank=True,
        help_text="The image will be displayed at the top left of the site 262px wide"
    )

    banner_image_dark = models.ImageField(
        verbose_name="Banner Image, Dark Theme", null=True, blank=True,
        help_text="An optional, alternate banner to be used with the dark theme."
    )

    site_logo = models.ImageField(
        verbose_name="Site Logo", null=True, blank=True,
        help_text="This will be displayed at the top left of your site's header (ideally 64x64 px)."
    )

    default_icon = models.ImageField(
        verbose_name="Default Icon", null=True, blank=True,
        help_text="This becomes the default icon for quests and badges and other places where icons are used (ideally 64x64 px)."
                  "If no icon is provided, it will fall back on the site logo (so you can leave this blank if you want to use your logo)"
    )

    favicon = models.ImageField(
        verbose_name="Favicon", null=True, blank=True,
        help_text="The image used in browser tabs (ideally 32x32 px). It will fall back to your site logo if a seperate favicon is not provided."
    )

    submission_quick_text = models.CharField(
        verbose_name="Submission Quick Text", blank=True, max_length=255,
        default="Please read the submission instructions more carefully. Thanks! ",
        help_text="Quickly insert this text into your replies with a button."
    )

    blank_approval_text = models.CharField(
        verbose_name="Approved without Comment Text", blank=True, max_length=255,
        default="(Approved - Your submission meets the criteria for this quest)",
        help_text="This text will be inserted when you approve a quest without commenting."
    )

    blank_return_text = models.CharField(
        verbose_name="Returned without Comment Text", blank=True, max_length=255,
        default="(Returned without comment)",
        help_text="This text will be inserted when you return a quest without commenting."
    )

    outgoing_email_signature = models.TextField(
        verbose_name="Outoging Email Signature", blank=True, max_length=512,
        help_text="Used when your deck sends your announcements and other notifications by email."
    )

    # closed = models.BooleanField(
    #     label="Closed for Maintenance", default=False, null=True, blank=True,
    #     help_text="This is close your site to students"
    # )

    deck_ai = models.ForeignKey(
        User, limit_choices_to={'is_staff': True},
        verbose_name="User for automated stuff", default=get_superadmin, on_delete=models.SET_DEFAULT,
        help_text="This user will appear as granting automatic badges, sending out announcements, and other automated actions. "
                  "Fun suggestion: create a new staff user named `R2-D2` or `Hal` or a similar AI name that fits the theme of your site."
    )

    active_semester = models.ForeignKey(
        'courses.Semester',
        verbose_name="Active Semester", default=get_active_semester, on_delete=models.PROTECT,
        help_text="Your currently active semester.  New semesters can be created from the admin menu."
    )

    # hs_chillax_line_active
    color_headers_by_mark = models.BooleanField(
        verbose_name="Activate Header Colors by Mark", default=False,
        help_text="Set up at least one Mark Range in admin for this to do anything."
    )

    enable_google_signin = models.BooleanField(
        verbose_name="Enable sign-in via Google",
        default=False,
        help_text=(
            "If you want to enable the ability to 'Sign in with Google' on your deck, please post a request "
            "<a href='https://github.com/bytedeck/bytedeck/discussions/1309' target='_blank'>here</a>"
        )
    )

    approve_oldest_first = models.BooleanField(
        verbose_name="Sort quests awaiting approval with oldest on top", default=False,
        help_text="Check this if you want to have the quest that have been waiting the longest to appear on top of the list."
    )

    display_marks_calculation = models.BooleanField(
        verbose_name="Use mark percentages", default=False,
        help_text='By default, the site only uses XP.  Check this if you also want to use percentages for student marks. \
            The conversion of XP to a percentage depends on several other settings in your deck.  \
            <a href="https://github.com/bytedeck/bytedeck/wiki/Using-Mark-Percentages" target="_blank">See here</a> for a full explanation. '
    )

    cap_marks_at_100_percent = models.BooleanField(
        verbose_name="Cap marks at 100%", default=False,
        help_text="By default, if a student has more than the expected XP in their course \
            (for the amount of time that has passed in the semester so far) their mark will show greater than 100%.  \
            Check this if you want to cap marks at 100%. This setting is only relevent if you are using mark percentages."
    )

    # Field to select custom name to change all instances of "announcement" to site-wide
    # Currently used in: announcements.forms, announcements.views, sidebar.html, and delete.html + list.html in announcements.templates
    custom_name_for_announcement = models.CharField(
        default="Announcement", max_length=20,
        help_text="A custom name specific to your deck to replace \"Announcement\". Annoucements are site-wide messages created \
            by staff members and displayed to all users through a tab in the sidebar. Alternatives might include \"Memo\", \
            \"Bulletin\", or \"Notice\", depending on your context."
    )

    # Field to select custom name to change all instances of "badge" to site-wide
    # Currently used in: sidebar.html, badges.forms, badges.views, badges.templates.list.html
    custom_name_for_badge = models.CharField(
        default="Badge", max_length=20,
        help_text="A custom name specific to your deck to replace \"Badge\". Badges are markers given to students either \
            automatically as a result of meeting a prerequisite, or manually by a staff user. Badges can grant students \
            XP, or act as prerequisites to other content. For example, \"Achievement\", \"Medal\", or \
            \"Certificate\" might be a more suitable name than Badge, depending on your context."
    )

    # Group is actually the Block model, but has been genericized and is now called Group
    custom_name_for_group = models.CharField(
        default="Group", max_length=20,
        help_text="A custom name specific to your deck to replace \"Group\".  Groups can be used to assign a group of students \
            to a specific teacher, and/or used as a prerequisite. For example, \"Block\", \"Cohort\", or \"Section\" \
            might be a more suitable name than Groups, depending on your context."
    )

    # Field to select custom name to change all instances of "student" to site-wide
    # Currently used in: profile_manager.forms, sidebar.html, and form.html + profile_list.html in profile_manager.templates
    custom_name_for_student = models.CharField(
        default="Student", max_length=20,
        help_text="A custom name specific to your deck to replace \"Student\". Students are non-staff site users, so this \
            setting should be changed to reflect the desired name for your deck's userbase. For example, \"User\", \"Member\" \
            or \"Learner\" might be a more suitable name than Student, depending on your context."
    )

    custom_name_for_tag = models.CharField(
        default="Tag", max_length=20,
        help_text="A custom name specific to your deck to replace \"Tag\".   For example, \"Competency\", \"Learning Outcome\", \
            or \"Skill\" might be a more suitable name, depending on how you use the Tags feature."
    )

    # Custom stylesheet and javascript
    #
    custom_stylesheet = RestrictedFileField(
        null=True, blank=True, content_types=['text/css', 'text/plain'], max_upload_size=512000,
        help_text="WARNING: This CSS stylesheet can be used to completely override the look and layout of your deck. \
            This feature also has the potential of making your deck unusable. Use at your own risk.",
    )
    custom_javascript = RestrictedFileField(
        null=True, blank=True, content_types=[
            'application/x-javascript', 'application/javascript', 'text/javascript'], max_upload_size=512000,
        help_text="WARNING: This custom JavaScript file can be used to completely override how the front end of your deck functions. \
            This feature also has the potential of making your deck unusable. Use at your own risk.",
    )

    deck_owner = models.ForeignKey(
        User, on_delete=models.PROTECT, default=get_default_deck_owner, limit_choices_to={'is_staff': True}, related_name="deck_owner",
        help_text="Only the current deck owner can change this setting."
    )

    def __str__(self):
        return self.site_name

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('config:site_config_update_own')

    def get_site_logo_url(self):
        if self.site_logo and hasattr(self.site_logo, 'url'):
            return self.site_logo.url
        else:
            return static('img/default_icon.png')

    def get_default_icon_url(self):
        if self.default_icon and hasattr(self.default_icon, 'url'):
            return self.default_icon.url
        else:
            return self.get_site_logo_url()

    def get_favicon_url(self):
        if self.favicon and hasattr(self.favicon, 'url'):
            return self.favicon.url
        elif self.site_logo and hasattr(self.site_logo, 'url'):
            return self.site_logo.url
        else:
            return static('icon/favicon.ico')

    def get_banner_image_url(self):
        if self.banner_image and hasattr(self.banner_image, 'url'):
            return self.banner_image.url
        else:
            return static('img/banner.png')

    def get_banner_image_dark_url(self):
        if self.banner_image_dark and hasattr(self.banner_image_dark, 'url'):
            return self.banner_image_dark.url
        elif self.banner_image and hasattr(self.banner_image, 'url'):
            return self.banner_image.url
        else:
            return static('img/banner.png')

    def set_active_semester(self, semester):
        from courses.models import Semester  # import here to prevent ciruclar imports

        # check if id or model object was given
        if isinstance(semester, Semester):
            self.active_semester = semester
        else:  # assume it's an id
            self.active_semester = get_object_or_404(Semester, id=semester)
        self.save()

    def _propagate_google_provider(self):
        """
        Copies the SocialApp config for GoogleProvider from the public schema down to
        the tenant's schema SocialApp
        """
        with schema_context(get_public_schema_name()):
            social_app = SocialApp.objects.get_current(provider=GoogleProvider.id)
            social_app_clone = copy(social_app)
            social_app_clone.pk = None

        # Sync the public SocialApps with the tenant SocialApp
        SocialApp.objects.filter(provider=GoogleProvider.id).delete()
        social_app_clone.save()
        social_app_clone.sites.add(Site.objects.get_current())

    @classmethod
    def cache_key(cls):
        return f'{connection.schema_name}-siteconfig'

    @classmethod
    def get(cls):
        """
        Used to access the single model instance for the current tenant/schema
        The SiteConfig object is create automatically via signal after new tenants are created.
        """

        if connection.schema_name != get_public_schema_name():
            siteconfig = cache.get(cls.cache_key())

            if not siteconfig:
                siteconfig = cls.objects.select_related('deck_ai', 'active_semester').get()
                cache.set(cls.cache_key(), siteconfig, 3600)

            return siteconfig

        return None


@receiver(post_save, sender=User)
@receiver(post_save, sender=SiteConfig)
@receiver(post_save, sender='courses.Semester')
def invalidate_siteconfig_cache_signal(sender, instance, **kwargs):
    """
    Whenever a `SiteConfig`, `Semester`, or `User` object is saved, we should invalidate the SiteConfig cache.
    """

    try:
        config = cache.get(SiteConfig.cache_key())
    except redis_exceptions.ConnectionError:
        # create_superuser is being called via manage.py initdb
        # This just prevents it from throwing an error when redis is not running
        # Because we are receiving a post_save from User, we don't want errors to happen
        config = None

    if not config:
        return

    for obj in (config, config.active_semester, config.deck_ai):
        # Only invalidate the cache when the instance we updated is the current one set in SiteConfig
        if instance == obj:
            cache.delete(SiteConfig.cache_key())
            break
    # cache.delete(SiteConfig.cache_key())
