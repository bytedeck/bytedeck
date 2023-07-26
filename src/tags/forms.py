from django import forms
from django.utils.text import slugify
from django.core.validators import validate_slug
from django.core.exceptions import ValidationError

from taggit.models import Tag

from .widgets import TaggitSelect2Widget


class BootstrapTaggitSelect2Widget(TaggitSelect2Widget):
    """A TaggitSelect2 widget with a bootstrap theme"""

    class Media:
        js = ('/static/js/select2-set-theme-bootstrap.js',)
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/select2-bootstrap-theme/0.1.0-beta.10/select2-bootstrap.min.css',)
        }


def validate_unique_slug(value):
    """
    Names that are not unique after being converted to a slug should be detected and rejected during validation
    i.e 'TEST-TAG' should not be accepted if tag named 'test-tag' exists, because names will be identical after processing, breaking unique=true
    """
    # check all tag objects for a slug identical to inputted name after being slugified
    duplicate_slug = Tag.objects.all().filter(slug=slugify(value))

    if duplicate_slug.exists():
        # if true, duplicate_slug is a 1-item queryset, calling .first() retrieves that item as a callable object
        raise ValidationError(f"Tag name too similar to existing tag: {duplicate_slug.first()}")


class TagForm(forms.ModelForm):

    class Meta:
        model = Tag
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].validators = [validate_slug, validate_unique_slug]
        self.fields['name'].help_text = 'Tags cannot contain spaces, use hyphens to create multi-word-tags-like-this'

    def save(self, *args):
        # will be saved on super func, assuming commit=True
        # save method override necessary since slug is unique=True, so we use unique name to generate a new slug to prevent duplicates
        # slugify name upon saving to keep consistency among all tag object names

        # save override necessary for update view to properly update tag slugs, assigning a tag with a changed name to an object will instead create
        # a new tag with the OLD name because tag slug hasn't changed
        self.instance.name = slugify(self.cleaned_data['name'])
        self.instance.slug = self.instance.name

        return super().save(*args)
