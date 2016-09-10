from badges.models import Badge
from courses.models import Semester

from django import forms
from django.contrib.auth.models import User
from djconfig.forms import ConfigForm


class HackerspaceConfigForm(ConfigForm):
    hs_closed = forms.BooleanField(label="Closed for Maintenance", initial=False,
                                   required=False)
    # hs_tour_on = forms.BooleanField(label="Activate Pop-up Welcome Tour",
    #                                 initial=False, required=False)
    # hs_view_active_semester_only = forms.BooleanField(label="View Students and Submissions from active semester only",
    #                                                   initial=False, required=False)
    hs_hackerspace_ai = forms.ModelChoiceField(label="User for automated stuff",
                                               queryset=User.objects.filter(is_staff=True), initial=1, required=True)

    hs_suggestion_badge = forms.ModelChoiceField(label="Suggestion Badge",
                                                 queryset=Badge.objects.all(), initial=1, required=True)

    hs_voting_badge = forms.ModelChoiceField(label="Voting Badge",
                                             queryset=Badge.objects.all(), initial=1, required=True)

    hs_num_votes = forms.IntegerField(label="Number of Votes Required for Badge",
                                      min_value=0, initial=5, required=True)

    hs_active_semester = forms.ModelChoiceField(label="Active Semester",
                                                queryset=Semester.objects.all(), initial=1, required=True)
    hs_chillax_line = forms.FloatField(label="Chillax Line %", initial=72.5,
                                       required=True)
    hs_chillax_line_active = forms.BooleanField(label="Activate Chillax Line", initial=False, required=False)
    hs_approve_oldest_first = forms.BooleanField(label="Sort quests awaiting approval with oldest on top",
                                                 initial=True, required=False)
    # hs_dark_theme = forms.BooleanField(label="Dark Theme (Experimental)",
    #                                    initial=False, required=False)

    def clean_hs_active_semester(self):
        # Untested, may not even work
        return self.cleaned_data['hs_active_semester'].pk

    def clean_hs_suggestion_badge(self):
        # Untested, may not even work
        return self.cleaned_data['hs_suggestion_badge'].pk

    def clean_hs_voting_badge(self):
        # Untested, may not even work
        return self.cleaned_data['hs_voting_badge'].pk

    def clean_hs_hackerspace_ai(self):
        # Untested, may not even work
        return self.cleaned_data['hs_hackerspace_ai'].pk
