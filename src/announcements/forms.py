from datetime import datetime

from django import forms
from django.utils import timezone

from bootstrap_datepicker_plus.widgets import DateTimePickerInput

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    # formfield_callback = make_custom_datetimefield

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['datetime_released'].initial = (
            datetime.now().strftime('%Y-%m-%d %H:%M')
        )

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
        archived = data.get('archived')

        if auto_publish and datetime_released < timezone.now():
            self.add_error("datetime_released", forms.ValidationError('An Announcement that is auto published cannot have a past release date.'))

        if auto_publish and archived:
            self.add_error("archived", forms.ValidationError('Cannot auto publish and archive an Announcement at the same time.'))

        return data
