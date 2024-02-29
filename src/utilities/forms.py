from django import forms
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.forms import FlatpageForm

from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

from .models import VideoResource, MenuItem


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


class CustomFlatpageForm(FlatpageForm):

    class Meta:
        model = FlatPage
        exclude = ('enable_comments', 'template_name',)

        widgets = {
            'content': ByteDeckSummernoteAdvancedInplaceWidget(),

            # https://code.djangoproject.com/ticket/24453
            'sites': forms.MultipleHiddenInput(),
        }


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = '__all__'

        # We are using forms.TextInput() for the URL here since the MenuItem.url is using the
        # URLOrRelativeURLField. The Django then renders this as `<input type="url">` which
        # prevents any user from entering relative urls on the browser.
        # That's why we just let the user enter any text or URL and let Django perform the validation
        widgets = {
            'url': forms.TextInput(),
        }
