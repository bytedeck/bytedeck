from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned
from django.db import models
from django.shortcuts import get_object_or_404
from django.templatetags.static import static


User = get_user_model()


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
        semester, created = Semester.objects.get_or_create(defaults={'active': True})
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

    site_logo = models.ImageField(
        verbose_name="Site Logo", null=True, blank=True, 
        help_text="This will be displayed at the top left of your site's header (ideally 256x256 px)."
    )

    banner_image = models.ImageField(
        verbose_name="Banner Image", null=True, blank=True,
        help_text="The banner will be displayed on your landing page and in a smaller format at the top left of the site (ideally 1140px wide)"
    )

    banner_image_dark = models.ImageField(
        verbose_name="Banner Image, Dark Theme", null=True, blank=True,
        help_text="An optional, alternate banner to be used with the dark theme."
    )

    default_icon = models.ImageField(
        verbose_name="Default Icon", null=True, blank=True, 
        help_text="This becomes the default icon for quests and badges and other places where icons are used (ideally 256x256 px)."
                  "If no icon is provided, it will fall back on the site logo (so you can leave this blank if you want to use your logo)"
    )

    favicon = models.ImageField(
        verbose_name="Favicon", null=True, blank=True,
        help_text="The image used in browser tabs (ideally 16x16 px). It will fall back to your site logo if a seperate favicon is not provided."
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

    # closed = models.BooleanField(
    #     label="Closed for Maintenance", default=False, null=True, blank=True,
    #     help_text="This is close your site to students"
    # )

    # hs_tour_on = forms.BooleanField(label="Activate Pop-up Welcome Tour",
    #                                 default=False, required=False)
    # hs_view_active_semester_only = forms.BooleanField(label="View Students and Submissions from active semester only",
    #                                                   default=False, required=False)
    deck_ai = models.ForeignKey(
        User, limit_choices_to={'is_staff': True},
        verbose_name="User for automated stuff", default=get_superadmin, on_delete=models.SET_DEFAULT, 
        help_text="This user will appear as granting automatic badges, sending out announcements, and other automated actions. "
                  "Fun suggestion: create a new staff user named `R2-D2` or `Hal` or a similar AI name that fits the theme of your site."
    )
    # hs_suggestions_on = forms.BooleanField(label="Turn on Suggestions", default=True,
    #                                        required=False)

    # hs_suggestion_badge = forms.ModelChoiceField(label="Suggestion Badge",
    #                                              queryset=Badge.objects.all(), default=1, required=True,
    #                                              help_text="This is only relevant if Suggestions are turned on.")

    # hs_voting_badge = forms.ModelChoiceField(label="Voting Badge",
    #                                          queryset=Badge.objects.all(), default=1, required=True,
    #                                          help_text="This is only relevant if Suggestions are turned on.")

    # hs_num_votes = forms.IntegerField(label="Number of Votes Required for Badge",
    #                                   min_value=0, default=5, required=True,
    #                                   help_text="This is only relevant if Suggestions are turned on.")

    active_semester = models.ForeignKey(
        'courses.Semester',
        verbose_name="Active Semester", default=get_active_semester, on_delete=models.SET_DEFAULT, 
        help_text="Your currently active semester.  New semesters can be created from the admin menu."
    )

    # hs_chillax_line = forms.FloatField(label="Chillax Line %", default=72.5,
    #                                    required=True)

    # hs_chillax_line_active
    color_headers_by_mark = models.BooleanField(
        verbose_name="Activate Header Colors by Mark", default=False,
        help_text="Set up at least one Mark Range in admin for this to do anything."
    )

    approve_oldest_first = models.BooleanField(
        verbose_name="Sort quests awaiting approval with oldest on top", default=False,
        help_text="Check this if you want to have the quest that have been waiting the longed to appear on top of the list."
    )
    # hs_message_teachers_only = forms.BooleanField(label="Limit students so they can only message teachers",
    #                                               default=True, required=False)

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
            return static('img/banner.svg')

    def get_banner_image_dark_url(self):
        if self.banner_image_dark and hasattr(self.banner_image_dark, 'url'):
            return self.banner_image_dark.url
        elif self.banner_image and hasattr(self.banner_image, 'url'):
            return self.banner_image.url
        else:
            return static('img/banner_slate.svg')

    def set_active_semester(self, semester):
        from courses.models import Semester  # import here to prevent ciruclar imports

        # check if id or model object was given
        if isinstance(semester, Semester):
            self.active_semester = semester
        else:  # assume it's an id
            self.active_semester = get_object_or_404(Semester, id=semester)
        self.save()

    @classmethod
    def get(cls):
        """ Used to access the single model instance for the current tenant/schema """

        # Create the settings instance for this tenant if it doesn't already exist
        obj, created = cls.objects.get_or_create()
        return obj
