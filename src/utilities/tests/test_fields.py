from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.utils import OperationalError, ProgrammingError
from django.test import SimpleTestCase

from queryset_sequence import QuerySetSequence

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from utilities.fields import FILE_MIME_TYPES, GFKChoiceField, RestrictedFileFormField, media_kind_of
from utilities.models import RestrictedFileField


User = get_user_model()


class GFKChoiceFieldTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create two users and a group spanning two content types for choice building."""
        cls.user1 = User.objects.create(username="johndoe", first_name="John", last_name="Doe")
        cls.user2 = User.objects.create(username="janedoe", first_name="Jane", last_name="Doe")
        cls.group1 = Group.objects.create(name="Editors")

    def _ct_pk(self, obj):
        """Return the "<content_type_pk>-<object_pk>" string the GFK choice field uses to identify obj."""
        return f"{ContentType.objects.get_for_model(obj).pk}-{obj.pk}"

    def test_GFKChoiceField__choices_and_clean(self):
        """Field groups choices by content type and clean() validates and resolves GFK values."""
        # order_by('pk') keeps the grouped-choices order deterministic: without
        # an explicit ordering Postgres returns rows in arbitrary order, so the
        # user sublist in the assertion below flaked intermittently in CI. The
        # field respects the caller's queryset order, so the fix belongs on the
        # queryset here rather than forcing an order inside the field.
        f = GFKChoiceField(
            queryset=QuerySetSequence(
                User.objects.filter(pk__in=[self.user1.pk, self.user2.pk]).order_by('pk'),
                Group.objects.filter(pk__in=[self.group1.pk]),
            ),
        )
        self.assertEqual(
            list(f.choices),
            [
                ("", "---------"),
                ("user", [
                    (self._ct_pk(self.user1), "johndoe"),
                    (self._ct_pk(self.user2), "janedoe"),
                ]),
                ("group", [
                    (self._ct_pk(self.group1), "Editors"),
                ]),
            ],
        )
        with self.assertRaises(ValidationError):
            f.clean("")
        with self.assertRaises(ValidationError):
            f.clean(None)
        with self.assertRaises(ValidationError):
            f.clean("-")

        # Invalid types that require TypeError to be caught.
        with self.assertRaises(ValidationError):
            f.clean([["fail"]])
        with self.assertRaises(ValidationError):
            f.clean([{"foo": "bar"}])

        self.assertEqual(f.clean(self._ct_pk(self.user2)).get_full_name(), "Jane Doe")
        self.assertEqual(f.clean(self._ct_pk(self.group1)).name, "Editors")

    def test_GFKChoiceField__empty_label_none_omits_blank_choice(self):
        """With empty_label=None the iterator does not yield the leading blank ('', label) choice."""
        f = GFKChoiceField(
            queryset=QuerySetSequence(User.objects.filter(pk=self.user1.pk)),
            empty_label=None,
        )
        choices = list(f.choices)
        # No leading ('', ...) blank option; the first (and only) group is the users group.
        self.assertNotIn('', [value for value, _ in choices])
        self.assertEqual(choices[0][0], 'user')

    def test_GFKChoiceField__clean_content_type_absent_from_queryset(self):
        """A value whose content type is valid but absent from the field's queryset is rejected.

        get_queryset_for_content_type finds no matching component queryset and returns None,
        so to_python raises invalid_choice rather than resolving an out-of-scope object.
        """
        # Field only offers Users; a Group value is a real ct-pk pair but out of scope.
        f = GFKChoiceField(queryset=QuerySetSequence(User.objects.filter(pk=self.user1.pk)))
        with self.assertRaises(ValidationError):
            f.clean(self._ct_pk(self.group1))

    def test_GFKChoiceField__clean_nonexistent_object_pk(self):
        """A value with an in-scope content type but a nonexistent object pk is rejected.

        The queryset.get(pk=...) lookup raises DoesNotExist, which to_python catches and
        re-raises as invalid_choice."""
        f = GFKChoiceField(queryset=QuerySetSequence(User.objects.filter(pk=self.user1.pk)))
        user_ct = ContentType.objects.get_for_model(User)
        with self.assertRaises(ValidationError):
            f.clean(f"{user_ct.pk}-9999999")

    def test_GFKChoiceField__prepare_value_passes_through_strings(self):
        """prepare_value returns a string value unchanged (Django passes both objects and
        already-prepared 'ctpk-objpk' strings through this method)."""
        f = GFKChoiceField(queryset=QuerySetSequence(User.objects.filter(pk=self.user1.pk)))
        self.assertEqual(f.prepare_value('3-5'), '3-5')


class RestrictedFileFieldTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Build a default and a content-type-restricted RestrictedFileField."""
        cls.default_file_field = RestrictedFileField()
        cls.image_file_field = RestrictedFileField(content_types=['image/jpeg', 'image/png'])

    def test_content_type__default_and_custom(self):
        "Ensure the default content type is 'All', and that the content type can be set correctly."

        # ensure default content type is 'All'
        self.assertEqual(self.default_file_field.content_types, 'All')

        # ensure content type is set correctly
        self.assertEqual(self.image_file_field.content_types, ['image/jpeg', 'image/png'])


class RestrictedFileFormFieldTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Build a default and a content-type-restricted RestrictedFileFormField."""
        cls.default_file_field = RestrictedFileFormField()
        cls.image_file_field = RestrictedFileFormField(content_types=['image/jpeg', 'image/png'])

    def test_content_type__default_and_custom(self):
        "Ensure the default content type is 'All', and that the content type can be set correctly."

        # ensure default content type is 'All'
        self.assertEqual(self.default_file_field.content_types, 'All')

        # ensure content type is set correctly
        self.assertEqual(self.image_file_field.content_types, ['image/jpeg', 'image/png'])

    def test_validate_file__accepts_the_types_browsers_send_for_wav_and_m4a(self):
        """An audio-restricted field takes a .wav or .m4a however the browser labels it (#2492).

        Browsers disagree on these formats' content types: a .wav arrives as `audio/wav` or
        `audio/x-wav`, and a .m4a as `audio/mp4` or `audio/x-m4a`. A question restricted to
        Audio must accept all four, or a student's recording is refused for its spelling.
        """
        field = RestrictedFileFormField(content_types=FILE_MIME_TYPES["audio"])
        for content_type in ("audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a"):
            with self.subTest(content_type=content_type):
                field.validate_file(SimpleNamespace(content_type=content_type, size=1))

    def test_validate_file__raises_when_over_max_size(self):
        """validate_file rejects an acceptable-type file whose size exceeds max_upload_size."""
        field = RestrictedFileFormField(content_types=['image/png'], max_upload_size=10)
        oversized = SimpleNamespace(content_type='image/png', size=11)
        with self.assertRaises(ValidationError):
            field.validate_file(oversized)

    def test_validate_file__accepts_a_normal_image(self):
        """A plain raster image is unaffected by the script-file block (#2559)."""
        field = RestrictedFileFormField(content_types=FILE_MIME_TYPES["image"])
        field.validate_file(SimpleNamespace(content_type="image/png", size=1, name="photo.png"))

    def test_validate_file__rejects_svg_uploaded_as_an_image(self):
        """An SVG is refused even by an image-restricted field: an SVG can carry a <script>
        that runs when the file is served inline, so it is a stored-XSS vector, not a safe
        image (#2559)."""
        field = RestrictedFileFormField(content_types=FILE_MIME_TYPES["image"])
        svg = SimpleNamespace(content_type="image/svg+xml", size=1, name="drawing.svg")
        with self.assertRaises(ValidationError):
            field.validate_file(svg)

    def test_validate_file__rejects_html_even_when_all_types_are_allowed(self):
        """A default ('All') field still refuses an HTML upload, which would run its script
        inline as stored XSS (#2559)."""
        field = RestrictedFileFormField()  # content_types == "All"
        html = SimpleNamespace(content_type="text/html", size=1, name="page.html")
        with self.assertRaises(ValidationError):
            field.validate_file(html)

    def test_validate_file__rejects_a_dangerous_extension_despite_a_spoofed_content_type(self):
        """The browser-declared content type is spoofable, so a .svg file is refused even when
        it claims to be a PNG: the extension is checked independently (#2559)."""
        field = RestrictedFileFormField()
        spoofed = SimpleNamespace(content_type="image/png", size=1, name="payload.svg")
        with self.assertRaises(ValidationError):
            field.validate_file(spoofed)

    def test_validate_file__rejects_a_stored_file_with_a_dangerous_extension_and_no_content_type(self):
        """A kept draft file is a stored FieldFile with no content_type; a dangerous extension
        is still caught from its name, so an SVG cannot slip through on resubmit (#2559)."""
        field = RestrictedFileFormField()
        stored = SimpleNamespace(size=1, name="uploads/payload.svg")  # no content_type attribute
        with self.assertRaises(ValidationError):
            field.validate_file(stored)

    def test_validate_file__rejects_an_unsafe_type_declared_with_parameters_or_odd_case(self):
        """A declared media type is matched by its type alone, whatever else it carries (#2559).

        ``Content-Type`` may append parameters and use any casing, so
        ``image/SVG+XML; charset=utf-8`` names the same type as ``image/svg+xml``. Comparing the
        raw header against the deny-list lets a safe-looking file name through on either
        spelling, so the type is normalised before the comparison.
        """
        field = RestrictedFileFormField()
        for declared in (
            "image/svg+xml; charset=utf-8",
            "IMAGE/SVG+XML",
            "  text/html ",
            "text/html;charset=UTF-8",
            "multipart/related; boundary=test",
            "message/rfc822",
        ):
            with self.subTest(content_type=declared):
                # a safe file name, so only the declared type can refuse this
                spoofed = SimpleNamespace(content_type=declared, size=1, name="homework.png")
                with self.assertRaises(ValidationError):
                    field.validate_file(spoofed)

    def test_validate_file__allow_markup_accepts_a_script_capable_file(self):
        """A field that opted in accepts HTML and SVG, by name and by declared type (#2559).

        The opt-in exists for a question a teacher set to the "web" file type, for a web or
        graphic design quest. Nothing else sets it, so nothing else accepts these.
        """
        field = RestrictedFileFormField(allow_markup=True)

        field.validate_file(SimpleNamespace(content_type="text/html", size=1, name="index.html"))
        field.validate_file(SimpleNamespace(content_type="image/svg+xml", size=1, name="logo.svg"))
        field.validate_file(SimpleNamespace(size=1, name="kept/logo.svg"))  # a kept draft file

    def test_validate_file__allow_markup_still_enforces_size_and_types(self):
        """Opting in lifts the script-capable refusal and nothing else.

        The field's own content_types allow-list and max_upload_size still apply, so a teacher
        turning this on for a web design question has not turned off every other check.
        """
        field = RestrictedFileFormField(allow_markup=True, max_upload_size=10)
        oversized = SimpleNamespace(content_type="text/html", size=11, name="index.html")
        with self.assertRaises(ValidationError):
            field.validate_file(oversized)

        restricted = RestrictedFileFormField(allow_markup=True, content_types=FILE_MIME_TYPES["image"])
        with self.assertRaises(ValidationError):
            restricted.validate_file(
                SimpleNamespace(content_type="application/zip", size=1, name="site.zip"))


class AllowedGFKChoiceFieldRebuildTest(ByteDeckTenantTestCase):
    """Regression tests for AllowedGFKChoiceField rebuilding its choices on copy.

    AllowedGFKChoiceField resolves its allowed models from the content-types
    table when the field object is constructed. Form fields are constructed at
    import time (when the form class body runs), which can happen before the
    database/tenant schema is ready -- e.g. while the test runner imports test
    modules to collect them -- leaving the field with an empty, all-invalid
    choice list cached for the whole process. Django copies declared fields into
    each form instance, so the field must rebuild its choices on deepcopy for
    forms to accept valid selections regardless of import timing.
    """

    def test_deepcopy__rebuilds_empty_import_time_queryset(self):
        """A field left empty at construction repopulates its choices when copied."""
        import copy

        from prerequisites.forms import PrereqGFKChoiceField
        from prerequisites.models import IsAPrereqMixin

        field = PrereqGFKChoiceField()
        # Simulate the import-time failure mode: the allowed-models lookup came
        # back empty (e.g. contenttypes not queryable when the field was built).
        field.queryset = QuerySetSequence()
        self.assertEqual(list(field.queryset.get_querysets()), [])

        # Django copies declared fields into each form instance
        # (BaseForm.__init__ deep-copies base_fields); the copy must rebuild
        # its choices against the live schema.
        copied = copy.deepcopy(field)
        models = [qs.model for qs in copied.queryset.get_querysets()]

        self.assertTrue(models, "deepcopy should have rebuilt a non-empty choice list")
        self.assertEqual(models, IsAPrereqMixin.all_registered_model_classes())

    def test_build_querysetsequence__survives_an_unqueryable_content_types_table(self):
        """A field built before the schema is ready gets an empty choice list instead of raising.

        This is the failure mode the rebuild-on-copy exists for: the allowed models are looked up
        from the content-types table, and a declared form field is constructed when its module is
        imported, which can precede the migrations that create that table. Each error the lookup
        can raise in that state is swallowed, and the deepcopy into a form instance fills the
        choices in later.
        """
        from prerequisites.forms import PrereqGFKChoiceField

        for error in (ContentType.DoesNotExist, ProgrammingError, OperationalError):
            with self.subTest(error=error.__name__):
                with patch.object(PrereqGFKChoiceField, 'get_allowed_model_classes', side_effect=error):
                    field = PrereqGFKChoiceField()

                self.assertEqual(list(field.queryset.get_querysets()), [])

    def test_form_instance__has_valid_choices_even_if_declared_field_is_empty(self):
        """A form using the field accepts a valid GFK selection through its copied field."""
        import copy

        from prerequisites.forms import PrereqFormInline, PrereqGFKChoiceField

        # Force the declared (import-time) field to be empty, then confirm a form
        # instance -- which deep-copies that field -- still resolves real choices.
        empty_field = PrereqGFKChoiceField()
        empty_field.queryset = QuerySetSequence()

        form_field = copy.deepcopy(empty_field)
        self.assertTrue([qs.model for qs in form_field.queryset.get_querysets()])

        # And a real form built from the declared fields resolves choices too.
        form = PrereqFormInline()
        self.assertTrue([qs.model for qs in form.fields['prereq_object'].queryset.get_querysets()])


class MediaKindOfTest(SimpleTestCase):
    """What `media_kind_of` says a stored file is, which decides how a page shows it (#2172)."""

    def test_media_kind_of__names_an_image(self):
        """An image the upload rules accept is reported as an image."""
        self.assertEqual(media_kind_of("uploads/my_drawing.png"), "image")
        self.assertEqual(media_kind_of("photo.JPEG"), "image")

    def test_media_kind_of__names_a_video(self):
        """A video is reported as a video, so a player is used rather than a picture."""
        self.assertEqual(media_kind_of("clips/demo.mp4"), "video")

    def test_media_kind_of__names_audio(self):
        """Audio is reported as audio: also playable, but with no picture to show."""
        self.assertEqual(media_kind_of("readings/chapter.mp3"), "audio")

    def test_media_kind_of__names_wav_and_m4a_recordings_as_audio(self):
        """The formats recorders actually produce are audio, whatever alias names them (#2492).

        A Windows or Audacity recording is a .wav, which Python's `mimetypes` reports as
        `audio/x-wav`, and a phone voice memo is a .m4a, reported as `audio/mp4`. Both must be
        recognised, or the answer is offered as a bare download link instead of a player.
        """
        self.assertEqual(media_kind_of("recordings/interview.wav"), "audio")
        self.assertEqual(media_kind_of("voice_memo.m4a"), "audio")

    def test_media_kind_of__says_nothing_about_other_files(self):
        """A file a browser cannot play is reported as nothing, and is offered as a link.

        The empty string covers both a type outside the lists (a PDF, an archive) and a name
        with no extension to go on, so a caller has one case to handle rather than two.
        """
        self.assertEqual(media_kind_of("notes.pdf"), "")
        self.assertEqual(media_kind_of("archive.zip"), "")
        self.assertEqual(media_kind_of("README"), "")

    def test_media_kind_of__only_accepts_types_the_upload_rules_do(self):
        """The answer is drawn from the same MIME lists a file-upload question validates with.

        A question restricted to images accepts exactly `IMAGE_MIME_TYPES`, so a file this
        reports as an image is one such a question would have taken: the two cannot drift,
        because they read the same list.
        """
        for mime_type, extension in (("image/png", ".png"), ("video/mp4", ".mp4"), ("audio/mpeg", ".mp3")):
            with self.subTest(mime_type=mime_type):
                self.assertIn(mime_type, FILE_MIME_TYPES["image"] + FILE_MIME_TYPES["video"] + FILE_MIME_TYPES["audio"])
                self.assertNotEqual(media_kind_of(f"file{extension}"), "")
