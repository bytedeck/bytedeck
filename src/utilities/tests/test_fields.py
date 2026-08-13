from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.utils import OperationalError, ProgrammingError

from queryset_sequence import QuerySetSequence

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from utilities.fields import GFKChoiceField, RestrictedFileFormField
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

    def test_validate_file__raises_when_over_max_size(self):
        """validate_file rejects an acceptable-type file whose size exceeds max_upload_size."""
        field = RestrictedFileFormField(content_types=['image/png'], max_upload_size=10)
        oversized = SimpleNamespace(content_type='image/png', size=11)
        with self.assertRaises(ValidationError):
            field.validate_file(oversized)


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

    def test_build__survives_the_content_types_table_not_being_queryable(self):
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
