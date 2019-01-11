from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget
from django import forms
from django.db import models
from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from .models import Announcement

# def make_custom_datetimefield(f):
#     formfield = f.formfield()
#     datetime_options = {
#         # 'format': 'dd-mm-yyyy HH:ii P',
#         'showMeridian': True,
#         'todayHighlight': True,
#         'minuteStep': 15,
#         'pickerPosition': 'bottom-left',
#         # 'minView': '1',
#     }
#
#     if isinstance(f, models.DateTimeField):
#         formfield.widget = DateTimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3)
#     elif isinstance(f, models.DateField):
#         formfield.widget = DateWidget(usel10n=True, options=datetime_options, bootstrap_version=3)
#     elif isinstance(f, models.TimeField):
#         formfield.widget = TimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3)
#     elif isinstance(f, models.TextField):
#         formfield.widget = SummernoteInplaceWidget()
#
#     return formfield


class AnnouncementForm(forms.ModelForm):
    # formfield_callback = make_custom_datetimefield

    class Meta:
        model = Announcement
        exclude = ['author']

        datetime_options = {
            # 'format': 'dd-mm-yyyy HH:ii P',
            'showMeridian': True,
            'todayHighlight': True,
            'minuteStep': 15,
            'pickerPosition': 'bottom-left',
            # 'minView': '1',
        }

        # TimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3)
        # DateWidget(usel10n=True, options=datetime_options, bootstrap_version=3)

        # SUMMERNOTE:
        # > If you don't like <iframe>, then use inplace widget
        # > Or if you're using django-crispy-forms, please use this.
        widgets = {
            'content': SummernoteInplaceWidget(),
            'sticky_until': DateTimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3),
            'datetime_released': DateTimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3),
            'datetime_expires': DateTimeWidget(usel10n=True, options=datetime_options, bootstrap_version=3),
        }


