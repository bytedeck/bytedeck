import six
import hashlib

from django import forms
from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIterator
from django.template.defaultfilters import filesizeformat


class ContentObjectChoiceIterator(ModelChoiceIterator):

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        for qs in self.queryset.get_querysets():
            yield (str(qs.model._meta.verbose_name), [self.choice(obj) for obj in qs])

    def choice(self, obj):
        return (self.field.prepare_value(obj), self.field.label_from_instance(obj))


class QuerySetSequenceFieldMixin(object):
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


class ContentObjectChoiceField(QuerySetSequenceFieldMixin, forms.ModelChoiceField):
    """
    Replacement for ModelChoiceField supporting QuerySetSequence choices.

    ContentObjectChoiceField expects options to look like::

        <option value="4">Model #4</option>

    With a ContentType of id 3 for that model, it becomes::

        <option value="3-4">Model #4</option>
    """

    iterator = ContentObjectChoiceIterator

    def prepare_value(self, value):
        """Return a ctypeid-objpk string for value."""
        if not value:
            return ''

        if isinstance(value, six.string_types):
            # Apparently Django's ModelChoiceField also expects two kinds of
            # "value" to be passed in this method.
            return value

        return '%s-%s' % (ContentType.objects.get_for_model(value).pk,
                          value.pk)

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


class CachedContentObjectChoiceIterator(ContentObjectChoiceIterator):

    def _cache_key(self, qs):
        """Cache key used to identify this query"""
        base_key = hashlib.md5(str(qs.query).encode('utf-8')).hexdigest()
        return cache.make_key('.'.join((qs.model._meta.db_table, 'queryset', base_key)), version=None)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        for qs in self.queryset.get_querysets():
            cache_key = self._cache_key(qs)
            choices = cache.get(cache_key, None)
            if choices is None:
                choices = [self.choice(obj) for obj in qs]
                cache.set(cache_key, choices, 500)
            yield (str(qs.model._meta.verbose_name), choices)


class CachedContentObjectChoiceField(ContentObjectChoiceField):
    iterator = CachedContentObjectChoiceIterator


# http://stackoverflow.com/questions/2472422/django-file-upload-size-limit
class RestrictedFileFormField(forms.FileField):

    def __init__(self, **kwargs):
        self.content_types = kwargs.pop("content_types", "All")
        self.max_upload_size = kwargs.pop("max_upload_size", 512000)
        super(RestrictedFileFormField, self).__init__(**kwargs)

    def clean(self, data, initial=None):
        file = super(RestrictedFileFormField, self).clean(data, initial)
        try:
            content_type = file.content_type
            if self.content_types == "All" or content_type in self.content_types:
                if file.size > self.max_upload_size:
                    raise ValidationError('Max filesize is %s. Current filesize %s' % (
                        filesizeformat(self.max_upload_size), filesizeformat(file.size))
                    )
            else:
                raise ValidationError('Filetype not supported. Acceptable filetypes are: %s' % (
                    str(self.content_types)))
        except AttributeError:
            pass

        return data
