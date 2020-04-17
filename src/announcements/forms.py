from datetime import datetime

from bootstrap_datepicker_plus import DateTimePickerInput
from django import forms
from django.utils import timezone
from django_summernote.widgets import SummernoteInplaceWidget

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    # formfield_callback = make_custom_datetimefield

    def __init__(self, *args, **kwargs):
        super(AnnouncementForm, self).__init__(*args, **kwargs)
        self.fields['datetime_released'].initial = (
            datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        # CELERY_BEAT BROKEN
        self.fields['auto_publish'].disabled = True  # remove after beat is fixed
        self.fields['auto_publish'].help_text = "Auto publishing of announcements is temporarily disabled. \
        Please manually publish with the 'Publish' button after saving an announcement as a draft."  # remove after beat is fixed

    class Meta:
        model = Announcement
        exclude = ['author']

        # SUMMERNOTE:
        # > If you don't like <iframe>, then use inplace widget
        # > Or if you're using django-crispy-forms, please use this.
        widgets = {
            'content': SummernoteInplaceWidget(),
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
                'An announcement that is auto published cannot have a past release date.'
            )
        return data
