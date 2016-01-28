from djconfig.forms import ConfigForm
from django import forms

from courses.models import Semester

class HackerspaceConfigForm(ConfigForm):
    hs_closed = forms.BooleanField(label = "Closed for Maintenance", initial = False,
            required = False)
    hs_tour_on = forms.BooleanField(label = "Activate Pop-up Welcome Tour",
        initial = False, required=False)
    hs_view_active_semester_only = forms.BooleanField(label = "View Students and Submissions from active semester only",
        initial = False, required=False)
    hs_active_semester = forms.ModelChoiceField(label = "Active Semester",
        queryset = Semester.objects.all(), initial=1, required=True)
    hs_chillax_line = forms.FloatField(label = "Chillax Line %", initial = 72.5,
            required = True)



    def clean_hs_active_semester(self):
        # Untested, may not even work
        return self.cleaned_data['hs_active_semester'].pk
