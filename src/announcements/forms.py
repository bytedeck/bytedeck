from datetime import datetime

from django import forms
from django.utils import timezone

from bootstrap_datepicker_plus.widgets import DateTimePickerInput

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

from .models import Announcement
from siteconfig.models import SiteConfig


class AnnouncementForm(forms.ModelForm):
    # formfield_callback = make_custom_datetimefield

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['datetime_released'].initial = (
            datetime.now().strftime('%Y-%m-%d %H:%M')
        )

        # Announcement creation/update settings that require name changes
        # Rename all instances of "Announcement" in announcement model field help text to value set in siteconfig custom_name_for_announcement field
        # These are all set almost verbatim in models, but we set them again here to use the correct custom name for announcements
        self.fields['datetime_released'].help_text = f"The time the {SiteConfig.get().custom_name_for_announcement.lower()} was published. \
            If auto_publish is True, then the {SiteConfig.get().custom_name_for_announcement.lower()} will automatically be published at this time."

        self.fields['auto_publish'].help_text = f"When set to true, the {SiteConfig.get().custom_name_for_announcement.lower()} will publish itself \
            on the date and time indicated."

        self.fields['draft'].help_text = f"A new {SiteConfig.get().custom_name_for_announcement.lower()} saved as a non-draft will be published and \
            notifications sent. Editing a previously saved draft will not send out notifications; use the Publish button on the \
            {SiteConfig.get().custom_name_for_announcement}s main page."

    class Meta:
        model = Announcement
        exclude = ['author', 'icon']

        # SUMMERNOTE:
        # > If you don't like <iframe>, then use inplace widget
        # > Or if you're using django-crispy-forms, please use this.
        widgets = {
            'content': ByteDeckSummernoteSafeInplaceWidget(),
            'sticky_until': DateTimePickerInput(format='%Y-%m-%d %H:%M'),
            'datetime_released': DateTimePickerInput(format='%Y-%m-%d %H:%M'),
            'datetime_expires': DateTimePickerInput(format='%Y-%m-%d %H:%M'),
        }

    def clean(self):
        data = self.cleaned_data

        auto_publish = data.get('auto_publish')
        datetime_released = data.get('datetime_released')

        if auto_publish and datetime_released < timezone.now():
            raise forms.ValidationError(
                f'An {SiteConfig.get().custom_name_for_announcement.lower()} that is auto published cannot have a past release date.'
            )
        return data
