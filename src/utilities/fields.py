from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.utils import OperationalError, ProgrammingError
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIterator
from django.template.defaultfilters import filesizeformat

from queryset_sequence import QuerySetSequence

from .widgets import GFKSelect2Widget


# common file MIME types to be uploaded by users
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_Types

IMAGE_MIME_TYPES = [
    'image/jpeg',  # JPEG images
    'image/png',   # PNG images
    'image/gif',   # GIF images
    'image/webp',  # WEBP images
    'image/tiff',  # TIFF images
    'image/bmp',   # BMP images
    'image/svg+xml'  # SVG vector images
]

VIDEO_MIME_TYPES = [
    'video/mp4',   # MP4 videos
    'video/webm',  # WebM videos
    'video/ogg',   # OGG videos
    'video/quicktime',  # MOV videos
    'video/x-msvideo',  # AVI videos
    'video/x-ms-wmv',  # WMV videos
    'video/mpeg',  # MPEG videos
    'video/3gpp',  # 3GP videos
    'video/3gpp2',  # 3G2 videos
    'video/x-flv',  # FLV videos
    'video/x-m4v'  # M4V videos
]

FILE_MIME_TYPES = {
    'image': IMAGE_MIME_TYPES,
    'video': VIDEO_MIME_TYPES,
    'media': IMAGE_MIME_TYPES + VIDEO_MIME_TYPES
}


class GFKChoiceIterator(ModelChoiceIterator):

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        for qs in self.queryset.get_querysets():
            yield (str(qs.model._meta.verbose_name), [self.choice(obj) for obj in qs])

    def choice(self, obj):
        return (self.field.prepare_value(obj), self.field.label_from_instance(obj))


class QuerySetSequenceFieldMixin:
    """Base methods for QuerySetSequence fields."""

    def get_queryset_for_content_type(self, content_type_id):
        """Return the QuerySet from the QuerySetSequence for a ctype."""
        content_type = ContentType.objects.get_for_id(content_type_id)

        for queryset in self.queryset.get_querysets():
            if queryset.model.__name__ == 'QuerySequenceModel':
                # django-queryset-sequence 0.7 support dynamically created
                # QuerySequenceModel which replaces the original model when it
                # patches the queryset since 6394e19
                model = queryset.model.__bases__[0]
            else:
                model = queryset.model

            if model == content_type.model_class():
                return queryset

    def raise_invalid_choice(self, params=None):
        """
        Raise a ValidationError for invalid_choice.

        The validation error left imprecise about the exact error for security
        reasons, to prevent an attacker doing information gathering to reverse
        valid content type and object ids.
        """
        raise forms.ValidationError(
            self.error_messages['invalid_choice'],
            code='invalid_choice',
            params=params,
        )

    def get_content_type_id_object_id(self, value):
        """Return a tuple of ctype id, object id for value."""
        return value.split('-', 1)


class GFKChoiceField(QuerySetSequenceFieldMixin, forms.ModelChoiceField):
    """
    Replacement for ModelChoiceField supporting QuerySetSequence choices.

    GFKChoiceField expects options to look like::

        <option value="4">Model #4</option>

    With a ContentType of id 3 for that model, it becomes::

        <option value="3-4">Model #4</option>
    """

    iterator = GFKChoiceIterator

    def prepare_value(self, value):
        """Return a ctypeid-objpk string for value."""
        if not value:
            return ''

        if isinstance(value, str):
            # Apparently Django's ModelChoiceField also expects two kinds of
            # "value" to be passed in this method.
            return value

        return f'{ContentType.objects.get_for_model(value).pk}-{value.pk}'

    def to_python(self, value):
        """
        Given a string like '3-5', return the model of ctype #3 and pk 5.

        Note that in the case of ModelChoiceField, to_python is also in charge
        of security, it's important to get the results from self.queryset.
        """
        if value in self.empty_values:
            return None

        try:
            content_type_id, object_id = self.get_content_type_id_object_id(value)
            queryset = self.get_queryset_for_content_type(content_type_id)
        except (AttributeError, ValueError):
            self.raise_invalid_choice()

        if queryset is None:
            self.raise_invalid_choice()

        try:
            return queryset.get(pk=object_id)
        except (ValueError, TypeError, queryset.model.DoesNotExist):
            self.raise_invalid_choice()

    def save_object_data(self, instance, name, value):
        """Set the attribute, for FutureModelForm."""
        setattr(instance, name, value)

    def value_from_object(self, instance, name):
        """Get the attribute, for FutureModelForm."""
        return getattr(instance, name)


class AllowedGFKChoiceField(GFKChoiceField):

    widget = GFKSelect2Widget

    def __init__(self, *args, **kwargs):
        model_classes = []
        try:
            model_classes = self.get_allowed_model_classes()
        except ContentType.DoesNotExist:
            # table doesn't exist yet
            pass
        except ProgrammingError:
            # django.db.utils.ProgrammingError: no such table:
            # django_content_type (e.g. postgresql)
            pass
        except OperationalError:
            # django.db.utils.OperationalError: no such table:
            # django_content_type (e.g. sqlite)
            pass

        querysetsequence = self.overridden_querysetsequence(
            QuerySetSequence(*[x.objects.all() for x in model_classes])
        )
        super().__init__(querysetsequence, *args, **kwargs)

        search_fields = {}
        for qs in self.queryset.get_querysets():
            klass = qs.model
            search_fields.setdefault(klass._meta.app_label, {}).update({
                klass._meta.model_name: klass.gfk_search_fields()
            })
        self.widget.search_fields = search_fields
        self.widget.attrs['data-placeholder'] = 'Type to search'

    def get_allowed_model_classes(self):
        """Returns a list of allowed Model classes"""
        raise NotImplementedError(
            '%s, must implement "get_allowed_model_classes" method.' % self.__class__.__name__
        )

    def overridden_querysetsequence(self, querysetsequence: QuerySetSequence) -> QuerySetSequence:
        """
        Returns overridden QuerySetSequence instance.

        Called inside __init__(), subclass should override for any actions to run.
        """
        return querysetsequence


# http://stackoverflow.com/questions/2472422/django-file-upload-size-limit
class RestrictedFileFormField(forms.FileField):

    def __init__(self, **kwargs):
        self.content_types = kwargs.pop("content_types", "All")
        self.max_upload_size = kwargs.pop("max_upload_size", 512000)
        super().__init__(**kwargs)

    def clean(self, data, initial=None):
        file = super().clean(data, initial)
        try:
            content_type = file.content_type
            if self.content_types == "All" or content_type in self.content_types:
                if file.size > self.max_upload_size:
                    raise ValidationError('Max filesize is {}. Current filesize {}'.format(
                        filesizeformat(self.max_upload_size), filesizeformat(file.size))
                    )
            else:
                raise ValidationError('Filetype not supported. Acceptable filetypes are: %s' % (
                    str(self.content_types)))
        except AttributeError:
            pass

        return data
