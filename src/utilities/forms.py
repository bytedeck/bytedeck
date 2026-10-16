from urllib.parse import unquote, urlsplit

from django import forms
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.forms import FlatpageForm
from django.urls import Resolver404, resolve

from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

from .fa_icon_widget import FontAwesomeIconPickerWidget
from .models import VideoResource, MenuItem


def path_has_a_page(path):
    """Return whether one of the app's url patterns matches ``path``, as it would a request's path."""
    try:
        resolve(path)
    except Resolver404:
        return False
    return True


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
    """Add/edit form for one of the links in the "Links" menu.

    The Font Awesome icon field uses the searchable icon picker
    (:class:`utilities.fa_icon_widget.FontAwesomeIconPickerWidget`), the same one the
    rank and badge type forms use, so the icon set is browsable rather than something
    a teacher has to know by heart.
    """

    class Meta:
        """Binds the URL text input and the icon picker onto the menu item's fields."""

        model = MenuItem
        fields = '__all__'

        # We are using forms.TextInput() for the URL here since the MenuItem.url is using the
        # URLOrRelativeURLField. The Django then renders this as `<input type="url">` which
        # prevents any user from entering relative urls on the browser.
        # That's why we just let the user enter any text or URL and let Django perform the validation
        widgets = {
            'url': forms.TextInput(),
            'fa_icon': FontAwesomeIconPickerWidget(),
        }
        labels = {
            # "Fa icon" is jargon; call it what it is.
            'fa_icon': 'Icon',
        }

    def clean_url(self):
        """Refuse a relative url that leads to no page in the app, such as a mistyped path.

        ``URLOrRelativeURLField`` only checks that a relative url (one starting with "/") is well formed,
        so a typo like "/courses/rank/" would save and put a link to a 404 in the menu (#1054). The path
        of a relative url has to match one of the app's url patterns, as a request's path would. The
        pattern is all it has to match: a link to a quest or custom page that doesn't exist still passes.

        Also let through:

        * a path missing its trailing slash, when the path with it matches: CommonMiddleware redirects
          the one to the other (APPEND_SLASH), so the link works;
        * paths to uploaded and static files, which the web server serves rather than a view;
        * absolute urls, which point at other sites.

        Returns:
            str: the url, unchanged.
        """
        url = self.cleaned_data['url']
        if not url.startswith('/'):
            return url

        path = unquote(urlsplit(url).path)
        if path.startswith((settings.MEDIA_URL, settings.STATIC_URL)):
            return url
        if not (path_has_a_page(path) or (not path.endswith('/') and path_has_a_page(path + '/'))):
            raise forms.ValidationError(
                'No page on this deck has the address "%(path)s". Check it for a typo, or copy it from '
                'the address bar of the page you want to link to.',
                code='no_page',
                params={'path': path},
            )
        return url
