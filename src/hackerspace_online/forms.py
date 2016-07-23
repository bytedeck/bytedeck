from courses.models import Semester

from django import forms
from djconfig.forms import ConfigForm


class HackerspaceConfigForm(ConfigForm):
    hs_closed = forms.BooleanField(label="Closed for Maintenance", initial=False,
                                   required=False)
    hs_tour_on = forms.BooleanField(label="Activate Pop-up Welcome Tour",
                                    initial=False, required=False)
    hs_view_active_semester_only = forms.BooleanField(label="View Students and Submissions from active semester only",
                                                      initial=False, required=False)
    hs_active_semester = forms.ModelChoiceField(label="Active Semester",
                                                queryset=Semester.objects.all(), initial=1, required=True)
    hs_chillax_line = forms.FloatField(label="Chillax Line %", initial=72.5,
                                       required=True)
    hs_chillax_line_active = forms.BooleanField(label="Activate Chillax Line",
                                                initial=False, required=False)
    hs_dark_theme = forms.BooleanField(label="Dark Theme (Experimental)",
                                       initial=False, required=False)

    def clean_hs_active_semester(self):
        # Untested, may not even work
        return self.cleaned_data['hs_active_semester'].pk
