import mimetypes
import os
from collections import namedtuple

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
    # SVG is absent from this list even though it is an image, because of how the list is used
    # rather than what SVG is: the pages that embed a file from it also link it at its storage
    # URL, and navigating to an SVG runs whatever <script> the XML carries (#2559). A question
    # can still ask for one, by ticking the script-capable opt-in below; that adds SVG to this
    # field's accepted types for that question alone, and the answer is shown through an <img>
    # (where browsers run no script) with a download link instead of a link into the site.
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

# WAV and M4A each go by two names: browsers disagree on the content type they send when
# one is uploaded, and Python's `mimetypes` (which `media_kind_of` guesses stored files
# with) uses `audio/x-wav` and `audio/mp4`. Both spellings of each are listed so a
# recording is accepted and played back whichever authority names it (#2492).
AUDIO_MIME_TYPES = [
    'audio/mpeg',  # MP3 audio
    'audio/ogg',   # OGG audio
    'audio/wav',   # WAV audio
    'audio/x-wav',  # WAV audio
    'audio/webm',  # WebM audio
    'audio/aac',   # AAC audio
    'audio/x-aiff',  # AIFF audio
    'audio/x-ms-wma',  # WMA audio
    'audio/x-m4a',  # M4A audio
    'audio/mp4',   # M4A audio
    'audio/flac',  # FLAC audio
]

# 'all' maps to the "All" sentinel that RestrictedFileFormField.validate_file
# treats as "accept any content type" (see its content_types == "All" check).
FILE_MIME_TYPES = {
    'image': IMAGE_MIME_TYPES,
    'video': VIDEO_MIME_TYPES,
    'audio': AUDIO_MIME_TYPES,
    'media': IMAGE_MIME_TYPES + VIDEO_MIME_TYPES,
    'all': 'All',
}

# Files that can carry a script a browser will run when it renders them inline from the app's
# own origin (the default, non-CDN media setup). An SVG or HTML upload with an embedded
# <script> runs in the viewer's session when someone opens it (a marker opening a student's
# file answer, typically): stored XSS. RestrictedFileFormField.validate_file refuses these
# from every upload, by extension and by declared type, unless the field names some of them
# in its `script_capable_types` (#2559).
UNSAFE_UPLOAD_EXTENSIONS = frozenset({
    '.svg', '.svgz', '.html', '.htm', '.xhtml', '.xht', '.shtml',
    '.xml', '.xsl', '.xslt', '.mhtml', '.mht',
})
UNSAFE_UPLOAD_MIME_TYPES = frozenset({
    'image/svg+xml', 'text/html', 'application/xhtml+xml',
    'application/xml', 'text/xml', 'text/xsl', 'application/xslt+xml',
    # MHTML: a whole page, script included, in one file. Browsers and Windows label it
    # several ways, so all of them are here.
    'multipart/related', 'message/rfc822', 'application/x-mimearchive',
})

#: The script-capable extensions and declared types that one upload field accepts anyway.
#: Both spellings travel together because a field has to allow both or neither: accepting
#: `image/svg+xml` while still refusing `.svg` (or the reverse) leaves the other spelling as
#: the way in, which is why `validate_file` checks the two separately in the first place.
ScriptCapableTypes = namedtuple("ScriptCapableTypes", "extensions mime_types")

#: The default every field gets: no script-capable file, whatever its content types allow.
NO_SCRIPT_CAPABLE_TYPES = ScriptCapableTypes(frozenset(), frozenset())

#: SVG alone, for a question that asks for an image and will take a vector one. `.svgz` comes
#: with it: it is the same format gzipped, and browsers declare it `image/svg+xml` too.
SVG_SCRIPT_CAPABLE_TYPES = ScriptCapableTypes(
    frozenset({'.svg', '.svgz'}),
    frozenset({'image/svg+xml'}),
)

#: All of them, for a question that asks for web files: a web design quest wants the HTML,
#: the stylesheet, the script and the SVG together, and browsers disagree about what several
#: of those are on upload, so nothing narrower would take the files it is asking for.
ALL_SCRIPT_CAPABLE_TYPES = ScriptCapableTypes(UNSAFE_UPLOAD_EXTENSIONS, UNSAFE_UPLOAD_MIME_TYPES)


def declared_mime_type(content_type):
    """Return the bare media type from a browser-declared ``Content-Type``.

    A declared type may carry parameters and any casing: ``image/SVG+XML; charset=utf-8``
    is the same type as ``image/svg+xml``, and only the part before the semicolon is the
    type itself. Comparing the raw string against a deny-list would miss both spellings.

    Args:
        content_type (str | None): the type as the browser declared it.

    Returns:
        str: the lower-cased media type with parameters and surrounding space removed,
        or "" when nothing was declared.
    """
    return (content_type or "").split(";")[0].strip().lower()


# Python's builtin MIME table does not know `.m4a`: platforms fill the gap from
# /etc/mime.types when that file exists, so the same recording guessed as `audio/mp4` on
# one machine and as nothing at all on another (CI's container has no such file).
# Register the mapping so `media_kind_of` answers the same everywhere (#2492).
mimetypes.add_type('audio/mp4', '.m4a')

# Which browser element can play a stored file, by the MIME types above. The value is the
# kind of media, so a template can pick between an image, a video player and an audio
# player without repeating the type lists.
_MEDIA_KINDS = (
    ('image', IMAGE_MIME_TYPES),
    ('video', VIDEO_MIME_TYPES),
    ('audio', AUDIO_MIME_TYPES),
)


def media_kind_of(file_name):
    """Say whether a stored file is an image, a video, an audio file, or none of those.

    The answer is guessed from the name, because that is all a page rendering a saved file
    has: the content type the browser sent is checked when the file is uploaded (see
    `RestrictedFileFormField.validate_file`) and not kept. The guess is measured against
    the same MIME lists that validation uses, so a file a question accepted as an image is
    the kind of file this reports as an image.

    Args:
        file_name (str): the stored file's name or path.

    Returns:
        str: 'image', 'video', 'audio', or '' for anything else (a PDF, a zip, a name with
        no extension to guess from).
    """
    mime_type = mimetypes.guess_type(file_name)[0] or ''

    for kind, mime_types in _MEDIA_KINDS:
        if mime_type in mime_types:
            return kind

    return ''


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
            model = queryset.model
            # django-queryset-sequence <0.8 dynamically created a QuerySequenceModel that
            # replaced the component model, so it had to be unwrapped to the real base model.
            # The pinned version (>=0.18) never creates QuerySequenceModel, so this guard is a
            # no-op safeguard for older library versions and cannot be exercised by the suite.
            if model.__name__ == 'QuerySequenceModel':  # pragma: no cover
                model = model.__bases__[0]

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
        querysetsequence = self._build_querysetsequence()
        super().__init__(querysetsequence, *args, **kwargs)
        self._configure_widget_search_fields()

    def _build_querysetsequence(self):
        """Resolve the allowed-models QuerySetSequence from the *current* DB state.

        The allowed models are looked up from the content-types table, so this
        can only succeed once that table exists and is queryable in the active
        schema. A field declared on a form class is constructed at *import time*
        (Django evaluates ``prereq_object = PrereqGFKChoiceField()`` when the
        form class body runs), which may happen before the database/tenant
        schema is ready — e.g. while the test runner is importing test modules
        to collect them. When that early lookup comes back empty the field would
        otherwise cache an empty (all-invalid) choice list for the life of the
        process, so every form instance copied from it rejects valid selections.

        To avoid that, this is called again from ``__deepcopy__``: Django copies
        the declared field into each form instance (``BaseForm.__init__`` does
        ``self.fields = copy.deepcopy(self.base_fields)``), so rebuilding on copy
        means every real form instance resolves its choices against the live
        schema at request time, regardless of when the field was first imported.
        """
        model_classes = []
        try:
            model_classes = self.get_allowed_model_classes()
        except (ContentType.DoesNotExist, ProgrammingError, OperationalError):
            # The content-types table isn't queryable yet (imported before
            # migrations, or no such table on postgres/sqlite). Leave the choice
            # list empty for now; the __deepcopy__ into a form instance rebuilds
            # it once the schema is available.
            pass

        return self.overridden_querysetsequence(
            QuerySetSequence(*[x.objects.all() for x in model_classes])
        )

    def _configure_widget_search_fields(self):
        """Populate the select2 widget's per-model search fields from the queryset."""
        search_fields = {}
        for qs in self.queryset.get_querysets():
            klass = qs.model
            search_fields.setdefault(klass._meta.app_label, {}).update({
                klass._meta.model_name: klass.gfk_search_fields()
            })
        self.widget.search_fields = search_fields
        self.widget.attrs['data-placeholder'] = 'Type to search'
        self.widget.attrs['data-theme'] = 'bootstrap'

    def __deepcopy__(self, memo):
        """Rebuild the allowed-models queryset when copied into a form instance.

        See ``_build_querysetsequence`` for why the import-time snapshot can't be
        trusted. ``ModelChoiceField.__deepcopy__`` copies the (possibly stale)
        queryset and widget; we then re-resolve both against the current schema.
        """
        result = super().__deepcopy__(memo)
        result.queryset = result._build_querysetsequence()
        result._configure_widget_search_fields()
        return result

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


class MultipleFileInput(forms.ClearableFileInput):

    allow_multiple_selected = True

    def __init__(self, *args, **kwargs):
        # Not sure why setting allow_multiple_selected = True doesn't work by itself.
        # Django docs don't say that attrs={'multiple': True} is also needed.

        # Make sure attrs dict exists, then set multiple to True so we can select more than one
        kwargs.setdefault('attrs', {})['multiple'] = True
        super().__init__(*args, **kwargs)


# http://stackoverflow.com/questions/2472422/django-file-upload-size-limit
class RestrictedFileFormField(forms.FileField):

    def __init__(self, *args, **kwargs):
        self.content_types = kwargs.pop("content_types", "All")
        self.max_upload_size = kwargs.pop("max_upload_size", 512000)
        # Which script-capable files this field takes anyway, for the questions that ask for
        # one: an image question willing to accept an SVG, or a web design question asking for
        # a page (#2559). Named types rather than a single "allow anything markup" flag, so a
        # question that asked for an SVG gets an SVG: under a blanket lift, `evil.html` sent as
        # `image/png` would pass both checks below and land in the image question's answers.
        self.script_capable_types = kwargs.pop("script_capable_types", NO_SCRIPT_CAPABLE_TYPES)
        super().__init__(*args, **kwargs)

    def validate_file(self, file):
        """Refuse an upload this field must not accept.

        Two rules, in this order. First, script-capable files (SVG, HTML, XML, MHTML) are
        refused unless this field named them in its ``script_capable_types``: served inline
        from the app's own origin they run their embedded script in the viewer's session,
        which is stored XSS against whoever opens the file, usually the marker (#2559). Both
        the file name and the browser-declared type are checked, because either one alone is
        trivially sidestepped: a spoofed ``Content-Type`` on a ``.svg``, or a declared
        ``image/svg+xml`` on a file named ``.png``. Second, the field's own ``content_types``
        allow-list and ``max_upload_size``.

        The two rules are independent, so allowing a script-capable type does not admit it
        past ``content_types``: a field that accepts SVG lists ``image/svg+xml`` in both.

        Args:
            file: the uploaded file, or the stored ``FieldFile`` Django's ``FileField.clean``
                returns when a form re-submits without choosing a new one. A stored file has
                no ``content_type``, so only the name-based rules apply to it.

        Raises:
            ValidationError: if the file is script-capable and this field does not allow it,
                if its declared type is outside ``content_types``, or if it is too large.
        """
        name = getattr(file, "name", "") or ""
        extension = os.path.splitext(name.lower())[1]
        if extension in UNSAFE_UPLOAD_EXTENSIONS and extension not in self.script_capable_types.extensions:
            raise ValidationError("For security reasons, this type of file cannot be uploaded.")

        try:
            content_type = declared_mime_type(file.content_type)
        except AttributeError:
            # A stored FieldFile has no content_type, so there is no declared type left to
            # check. Its name was checked above, against the rules in force right now.
            return

        if content_type in UNSAFE_UPLOAD_MIME_TYPES and content_type not in self.script_capable_types.mime_types:
            raise ValidationError("For security reasons, this type of file cannot be uploaded.")

        if self.content_types == "All" or content_type in self.content_types:
            if file.size > self.max_upload_size:
                raise ValidationError(
                    "Max filesize is {}. Current filesize {}".format(
                        filesizeformat(self.max_upload_size),
                        filesizeformat(file.size),
                    )
                )
        else:
            raise ValidationError(
                "Filetype not supported. Acceptable filetypes are: %s"
                % (str(self.content_types))
            )

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            files = [single_file_clean(d, initial) for d in data]
        else:
            files = [single_file_clean(data, initial)]

        for file in files:
            self.validate_file(file)

        return files if isinstance(data, (list, tuple)) else files[0]


class RestrictedMultiFileFormField(RestrictedFileFormField):
    """Adds multi-file upload capability to the RestrictedFileFormField

    To use this the form will need to deal with the files as suggested in
    https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/#uploading-multiple-files

    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)
