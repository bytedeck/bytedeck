from bootstrap_datepicker_plus import DateTimePickerInput
from django import forms
from django.utils import timezone
from django_summernote.widgets import SummernoteInplaceWidget

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    # formfield_callback = make_custom_datetimefield

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
