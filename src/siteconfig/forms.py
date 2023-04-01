from django import forms
from django.contrib.auth import get_user_model

from .models import SiteConfig

User = get_user_model()


class SiteConfigForm(forms.ModelForm):

    class Meta:
        model = SiteConfig
        # active_semester setting moved to Semester views.
        exclude = ["active_semester"]

    def __init__(self, *args, **kwargs):
        is_deck_owner = kwargs.pop('is_deck_owner', False)

        super().__init__(*args, **kwargs)

        if not is_deck_owner:
            self.fields['deck_owner'].disabled = True

        self.fields['enable_google_signin'].disabled = True
