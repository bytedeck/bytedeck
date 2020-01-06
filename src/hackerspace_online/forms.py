

from django import forms
from django.contrib.auth.models import User
from djconfig.forms import ConfigForm

from allauth.account.forms import SignupForm

from utilities.models import ImageResource
from badges.models import Badge
from courses.models import Semester


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(
        max_length=30, 
        label='First name',
        help_text="Please use the name that matches your school records.  You can put a different name in your profile.")  # noqa
    last_name = forms.CharField(
        max_length=30, 
        label='Last name',
        help_text='Please use the name that matches your school records.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = 'Your student number, if you are a student.'

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        return user


class HackerspaceConfigForm(ConfigForm):

    hs_site_name = forms.CharField(label="Site Name, Full", initial="Timberline's Digital Hackerspace", required=True,
                                   max_length=50, help_text="This name will appear throughout the site.")

    hs_site_name_short = forms.CharField(label="Site Name, Short", initial="Hackerspace", required=True,
                                         max_length=20, help_text="Used when the full site name is too cumbersome.")

    hs_site_logo = forms.ModelChoiceField(label="Site Logo", required=False, queryset=ImageResource.objects.all(),
                                          help_text="Selected from images uploaded via Admin through the "
                                                    "Utilies > Image Resources model.")

    hs_banner_image = forms.ModelChoiceField(label="Banner Image", required=False,
                                             queryset=ImageResource.objects.all(),
                                             help_text="Selected from images uploaded via Admin through the "
                                                       "Utilies > Image Resources model.")

    hs_banner_image_dark = forms.ModelChoiceField(label="Banner Image, Dark Theme", required=False,
                                                  queryset=ImageResource.objects.all(),
                                                  help_text="Same as above but used for the dark theme.")

    hs_default_icon = forms.ModelChoiceField(label="Default Icon", required=False, queryset=ImageResource.objects.all(),
                                             help_text="Selected from images uploaded via Admin through the "
                                                       "Utilies > Image Resources model.  "
                                                       "This becomes the default icon for quests and badges.")

    hs_favicon = forms.ModelChoiceField(label="Favicon", required=False, queryset=ImageResource.objects.all(),
                                        help_text="Selected from images uploaded via Admin through the "
                                                  "Utilies > Image Resources model.")

    hs_submission_quick_text = forms.CharField(
        label="Submission Quick Text", 
        initial="Please read the submission instructions more carefully. Thanks! ",
        required=True,
        max_length=255, 
        help_text="Quickly insert this text into your replies with a button.")

    hs_blank_approval_text = forms.CharField(
        label="Approved Without Comment Text", 
        initial="(Approved - Your submission meets the criteria for this quest)",
        required=False,
        max_length=255, 
        help_text="This text will be inserted when you approve a quest without commenting.")

    hs_blank_return_text = forms.CharField(
        label="Returned Without Comment Text", 
        initial="(Returned without comment)",
        required=False,
        max_length=255, 
        help_text="This text will be inserted when you return a quest without commenting.")

    hs_closed = forms.BooleanField(label="Closed for Maintenance", initial=False,
                                   required=False)
    # hs_tour_on = forms.BooleanField(label="Activate Pop-up Welcome Tour",
    #                                 initial=False, required=False)
    # hs_view_active_semester_only = forms.BooleanField(label="View Students and Submissions from active semester only",
    #                                                   initial=False, required=False)
    hs_hackerspace_ai = forms.ModelChoiceField(
        label="User for automated stuff",
        queryset=User.objects.filter(is_staff=True), initial=1, required=True,
        help_text="This user will appear as granted automatic badges etc. "
                  "Suggestion: create a new staff user named `Hackerspace_AI` or similar.")
    hs_suggestions_on = forms.BooleanField(label="Turn on Suggestions", initial=True,
                                           required=False)

    hs_suggestion_badge = forms.ModelChoiceField(label="Suggestion Badge",
                                                 queryset=Badge.objects.all(), initial=1, required=True,
                                                 help_text="This is only relevant if Suggestions are turned on.")

    hs_voting_badge = forms.ModelChoiceField(label="Voting Badge",
                                             queryset=Badge.objects.all(), initial=1, required=True,
                                             help_text="This is only relevant if Suggestions are turned on.")

    hs_num_votes = forms.IntegerField(label="Number of Votes Required for Badge",
                                      min_value=0, initial=5, required=True,
                                      help_text="This is only relevant if Suggestions are turned on.")

    hs_active_semester = forms.ModelChoiceField(label="Active Semester",
                                                queryset=Semester.objects.all(), initial=1, required=True)
    # hs_chillax_line = forms.FloatField(label="Chillax Line %", initial=72.5,
    #                                    required=True)
    hs_chillax_line_active = forms.BooleanField(
        label="Activate Header Colors by Mark", initial=False, required=False,
        help_text="Set up at least one Mark Range in admin for this to do anything."
    )
    hs_approve_oldest_first = forms.BooleanField(label="Sort quests awaiting approval with oldest on top",
                                                 initial=True, required=False)
    hs_message_teachers_only = forms.BooleanField(label="Limit students so they can only message teachers",
                                                  initial=True, required=False)

    def clean_hs_active_semester(self):
        return self.cleaned_data['hs_active_semester'].pk

    def clean_hs_suggestion_badge(self):
        return self.cleaned_data['hs_suggestion_badge'].pk

    def clean_hs_voting_badge(self):
        return self.cleaned_data['hs_voting_badge'].pk

    def clean_hs_hackerspace_ai(self):
        return self.cleaned_data['hs_hackerspace_ai'].pk

    def clean_hs_banner_image(self):
        if self.cleaned_data['hs_banner_image']:
            return self.cleaned_data['hs_banner_image'].pk
        else:
            return None

    def clean_hs_banner_image_dark(self):
        if self.cleaned_data['hs_banner_image_dark']:
            return self.cleaned_data['hs_banner_image_dark'].pk
        else:
            return None

    def clean_hs_site_logo(self):
        if self.cleaned_data['hs_site_logo']:
            return self.cleaned_data['hs_site_logo'].pk
        else:
            return None

    def clean_hs_default_icon(self):
        if self.cleaned_data['hs_default_icon']:
            return self.cleaned_data['hs_default_icon'].pk
        else:
            return None
