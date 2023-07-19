from django import forms
from django.utils.text import slugify
from django.core.validators import validate_slug

from taggit.models import Tag

from .widgets import TaggitSelect2Widget


class BootstrapTaggitSelect2Widget(TaggitSelect2Widget):
    """A TaggitSelect2 widget with a bootstrap theme"""

    class Media:
        js = ('/static/js/select2-set-theme-bootstrap.js',)
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/select2-bootstrap-theme/0.1.0-beta.10/select2-bootstrap.min.css',)
        }


class TagForm(forms.ModelForm):

    class Meta:
        model = Tag
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].validators = [validate_slug]
        self.fields['name'].help_text = 'Tags cannot contain spaces, use hyphens to create multi-word-tags-like-this'

    def save(self, *args):
        # will be saved on super func, assuming commit=True
        # save method override necessary since slug is unique=True, so we use unique name to generate a new slug to prevent possible duplicates
        # without it, updating a tag and assigning it to an object will actually re-create the OLD tag and assign that instead...
        self.instance.slug = slugify(self.cleaned_data['name'])

        return super().save(*args)
