from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.forms import FlatpageForm
from django_summernote.widgets import SummernoteInplaceWidget, SummernoteWidget
from django_summernote.fields import SummernoteTextField
from django.utils.translation import gettext, gettext_lazy as _

from utilities.models import VideoResource


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

# http://k


class CustomFlatpageForm(forms.ModelForm):
    url = forms.RegexField(
        label=_("URL"),
        max_length=100,
        regex=r'^[-\w/\.~]+$',
        help_text=_('Example: “/about/contact/”. Make sure to have leading and trailing slashes.'),
        error_messages={
            "invalid": _(
                "This value must contain only letters, numbers, dots, "
                "underscores, dashes, slashes or tildes."
            ),
        },
    )
    content = SummernoteTextField()

    class Meta:
        model = FlatPage
        exclude = ('enable_comments', 'sites', 'templates',)

        widget = {
            'content': SummernoteInplaceWidget(),
        }

    def __init__(self, *args, **kwargs):
        super(CustomFlatpageForm, self).__init__(*args, **kwargs)

        if not self._trailing_slash_required():
            self.fields['url'].help_text = _( 'Example: “/about/contact”. Make sure to have a leading slash.' )

    def _trailing_slash_required(self):
        return (
            settings.APPEND_SLASH and
            'django.middleware.common.CommonMiddleware' in settings.MIDDLEWARE
        )

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

    def clean(self):
        url = self.cleaned_data.get('url')
        sites = self.cleaned_data.get('sites')

        same_url = FlatPage.objects.filter(url=url)
        if self.instance.pk:
            same_url = same_url.exclude(pk=self.instance.pk)

        if sites and same_url.filter(sites__in=sites).exists():
            for site in sites:
                if same_url.filter(sites=site).exists():
                    raise ValidationError(
                        _('Flatpage with url %(url)s already exists for site %(site)s'),
                        code='duplicate_url',
                        params={'url': url, 'site': site},
                    )

        return super(CustomFlatpageForm, self).clean()