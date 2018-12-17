from django import forms
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat



# http://stackoverflow.com/questions/2472422/django-file-upload-size-limit
class RestrictedFileFormField(forms.FileField):

    def __init__(self, **kwargs):
        self.content_types = kwargs.pop("content_types")
        self.max_upload_size = kwargs.pop("max_upload_size")

        super(RestrictedFileFormField, self).__init__(**kwargs)

    def clean(self, data, initial=None):
        file = super(RestrictedFileFormField, self).clean(data, initial)
        try:
            content_type = file.content_type
            if content_type in self.content_types:
                if file._size > self.max_upload_size:
                    raise ValidationError(_('Max filesize is %s. Current filesize %s') % (
                        filesizeformat(self.max_upload_size), filesizeformat(file._size)))
            else:
                    raise ValidationError(_('Filetype not supported. Acceptable filetypes are: %s') % (
                        str(self.content_types)))
        except AttributeError:
            pass

        return data