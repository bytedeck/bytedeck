from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

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
        return f"{ContentType.objects.get_for_model(obj).pk}-{obj.pk}"

    def test_GFKChoiceField__choices_and_clean(self):
        """Field groups choices by content type and clean() validates and resolves GFK values."""
        f = GFKChoiceField(
            queryset=QuerySetSequence(
                User.objects.filter(pk__in=[self.user1.pk, self.user2.pk]),
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
