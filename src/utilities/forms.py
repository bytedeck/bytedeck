from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.forms import FlatpageForm
from django.utils.translation import gettext, gettext_lazy as _
from django_summernote.widgets import SummernoteInplaceWidget

from utilities.models import VideoResource, MenuItem


class FutureModelForm(forms.ModelForm):
    """
    ModelForm which adds extra API to form fields.

    Form fields may define new methods for FutureModelForm:

    - ``FormField.value_from_object(instance, name)`` should return the initial
      value to use in the form, overrides ``ModelField.value_from_object()``
      which is what ModelForm uses by default,
    - ``FormField.save_object_data(instance, name, value)`` should set instance
      attributes. Called by ``save()`` **before** writing the database, when
      ``instance.pk`` may not be set, it overrides
      ``ModelField.save_form_data()`` which is normally used in this occasion
      for non-m2m and non-virtual model fields.

    """

    def __init__(self, *args, **kwargs):
        """Override that uses a form field's ``value_from_object()``."""
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if not hasattr(field, 'value_from_object'):
                continue

            try:
                self.initial[name] = field.value_from_object(self.instance, name)
            except:  # noqa
                continue

    def _post_clean(self):
        """Override that uses the form field's ``save_object_data()``."""
        super()._post_clean()

        for name, field in self.fields.items():
            if not hasattr(field, 'save_object_data'):
                continue

            value = self.cleaned_data.get(name, None)
            if value:
                field.save_object_data(self.instance, name, value)


class VideoForm(forms.ModelForm):
    class Meta:
        model = VideoResource
        fields = ["title", "video_file"]


class MultiFileInput(forms.FileInput):
    def render(self, name, value, attrs={}):
        attrs['multiple'] = 'multiple'
        # attrs['class'] += 'btn'
        return super(MultiFileInput, self).render(name, None, attrs=attrs)

    def value_from_datadict(self, data, files, name):
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        else:
            return [files.get(name)]


class MultiFileField(forms.FileField):
    widget = MultiFileInput
    default_error_messages = {
        'min_num': u"Ensure at least %(min_num)s files are uploaded (received %(num_files)s).",
        'max_num': u"Ensure at most %(max_num)s files are uploaded (received %(num_files)s).",
        'file_size': u"File: %(uploaded_file_name)s, exceeded maximum upload size."
    }

    def __init__(self, *args, **kwargs):
        self.min_num = kwargs.pop('min_num', 0)
        self.max_num = kwargs.pop('max_num', None)
        self.maximum_file_size = kwargs.pop('maximum_file_size', None)
        super(MultiFileField, self).__init__(*args, **kwargs)

    def to_python(self, data):
        ret = []
        for item in data:
            ret.append(super(MultiFileField, self).to_python(item))
        return ret

    # def validate(self, data):
    #     super(MultiFileField, self).validate(data)
    #     num_files = len(data)
    #     if len(data) and not data[0]:
    #         num_files = 0
    #     if num_files < self.min_num:
    #         raise ValidationError(self.error_messages['min_num'] % {'min_num': self.min_num, 'num_files': num_files})
    #         return
    #     elif self.max_num and  num_files > self.max_num:
    #         raise ValidationError(self.error_messages['max_num'] % {'max_num': self.max_num, 'num_files': num_files})
    #     for uploaded_file in data:
    #         if uploaded_file.size > self.maximum_file_size:
    #             raise ValidationError(self.error_messages['file_size'] % { 'uploaded_file_name': uploaded_file.name})

    def clean(self, data, initial=None):
        super(MultiFileField, self).clean(data, initial=None)
        num_files = len(data)
        if len(data) and not data[0]:
            num_files = 0
        if num_files < self.min_num:
            raise ValidationError(self.error_messages['min_num'] % {'min_num': self.min_num, 'num_files': num_files})
            return
        elif self.max_num and num_files > self.max_num:
            raise ValidationError(self.error_messages['max_num'] % {'max_num': self.max_num, 'num_files': num_files})
        if num_files > 0:
            for uploaded_file in data:
                if uploaded_file.size > self.maximum_file_size:
                    raise ValidationError(self.error_messages['file_size'] % {'uploaded_file_name': uploaded_file.name})
        return data

        # def clean(self, data, initial=None):
        #     super(MultiFileField, self).clean(data, initial)
        #     try:
        #         # content_type = file.content_type
        #         # if content_type in self.content_types:
        #         if file._size > self.max_upload_size:
        #             raise ValidationError(_('Please keep filesize under %s. Current filesize %s') % (
        #                 filesizeformat(self.max_upload_size), filesizeformat(file._size)))
        #         # else:
        #             # raise ValidationError(_('Filetype not supported.'))
        #     except AttributeError:
        #         pass


class CustomFlatpageForm(FlatpageForm):

    class Meta:
        model = FlatPage
        exclude = ('enable_comments', 'template_name',)

        widgets = {
            'content': SummernoteInplaceWidget(),
            
            # https://code.djangoproject.com/ticket/24453
            'sites': forms.MultipleHiddenInput(),
        }


class MenuItemForm(forms.ModelForm):

    class Meta:
        model = MenuItem
        fields = '__all__'

    # needed to accept relative urls on frontend, URLOrRelativeURLField() doesn't work for some reason...
    # duplicated from django.contrib.flatpages.forms.FlatPageForm save for url help text
    url = forms.RegexField(
        label=_(MenuItem._meta.get_field('url').verbose_name),
        max_length=100,
        regex=r'^[-\w/\.~]+$',
        help_text=_(MenuItem._meta.get_field('url').help_text),
        error_messages={
            "invalid": _(
                "This value must contain only letters, numbers, dots, "
                "underscores, dashes, slashes or tildes."
            ),
        },
    )

    # checks if a trailing slash is required according to the project settings
    # duplicated from django.contrib.flatpages.forms.FlatPageForm
    def _trailing_slash_required(self):
        return (
            settings.APPEND_SLASH and
            'django.middleware.common.CommonMiddleware' in settings.MIDDLEWARE
        )

    # checks for leading or trailing urls and displays according error text
    # duplicated from django.contrib.flatpages.forms.FlatPageForm
    def clean_url(self):
        url = self.cleaned_data['url']
        if not url.startswith('/'):
            raise ValidationError(
                gettext("URL is missing a leading slash."),
                code='missing_leading_slash',
            )
        if self._trailing_slash_required() and not url.endswith('/'):
            raise ValidationError(
                gettext("URL is missing a trailing slash."),
                code='missing_trailing_slash',
            )
        return url
