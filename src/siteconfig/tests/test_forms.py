from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile

from django_tenants.test.cases import TenantTestCase

from siteconfig.models import SiteConfig
from siteconfig.forms import SiteConfigForm

from hackerspace_online.tests.utils import generate_form_data, model_to_form_data


class SiteConfigFormTest(TenantTestCase):
    """Tests for the SiteConfig Form
    """

    def setUp(self):
        """TenantTestCase generates a tenant for tests.
        Each tenant should have a single SiteConfig object
        that is created upon first access via the get() method.
        """
        self.config = SiteConfig.get()

    def test_clean_custom_stylesheet_method(self):
        """
        Tests CSS validation for form uploads done by `clean_custom_stylesheet` method.
        """
        form_data = model_to_form_data(self.config, SiteConfigForm)
        del form_data["custom_stylesheet"]

        # trying to upload "wrong" content,
        # here "wrong" content means any textual, but non-stylesheet content
        wrong_content = b"""Lorem ipsum dolor sit amet..."""
        custom_stylesheet = InMemoryUploadedFile(
            BytesIO(wrong_content),
            field_name="tempfile",
            name="custom.md",
            content_type='text/plain',
            size=len(wrong_content),
            charset="utf-8",
        )
        form = SiteConfigForm(form_data, files={"custom_stylesheet": custom_stylesheet}, instance=self.config)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "CSSStyleRule: No start { of style declaration found: 'Lorem ipsum dolor sit amet...' [1:30: ]",
            form.errors["custom_stylesheet"],
        )

        # trying to upload "invalid" stylesheet,
        # here "invalid" stylesheet means any stylesheet content, but with syntax errors
        invalid_css = b"""body { colour: bleck; }"""
        custom_stylesheet = InMemoryUploadedFile(
            BytesIO(invalid_css),
            field_name="tempfile",
            name="custom.css",
            content_type='text/css',
            size=len(invalid_css),
            charset="utf-8",
        )
        form = SiteConfigForm(form_data, files={"custom_stylesheet": custom_stylesheet}, instance=self.config)
        self.assertFalse(form.is_valid())
        self.assertIn("This stylesheet is not valid CSS.", form.errors["custom_stylesheet"])

        # trying to upload "correct" stylesheet
        valid_css = b"""body { color: black; }"""
        custom_stylesheet = InMemoryUploadedFile(
            BytesIO(valid_css),
            field_name="tempfile",
            name="custom.css",
            content_type='text/css',
            size=len(valid_css),
            charset="utf-8",
        )
        form = SiteConfigForm(form_data, files={"custom_stylesheet": custom_stylesheet}, instance=self.config)
        self.assertTrue(form.is_valid())

    def test_custom_stylesheet_file_submission_removal(self):
        """
        Custom CSS file can be uploaded (submitted) and attached to `SiteConfig` model,
        and existing file can be cleared.
        """
        valid_css = b"""body { color: black; }"""
        custom_stylesheet = InMemoryUploadedFile(
            BytesIO(valid_css),
            field_name="tempfile",
            name="custom.css",
            content_type='text/css',
            size=len(valid_css),
            charset="utf-8",
        )

        form_data = generate_form_data(model_form=SiteConfigForm)

        # First case, custom stylesheet can be uploaded and attached to `SiteConfig` object

        # assert there is no saved files, ie. "reading" non-existing file should raise an exception
        with self.assertRaises(ValueError):
            SiteConfig.get().custom_stylesheet.read()
        form = SiteConfigForm(
            form_data, files={"custom_stylesheet": custom_stylesheet}, instance=self.config,
            is_deck_owner=True,
        )
        form.save()
        self.assertTrue(form.is_valid())
        self.assertEqual(SiteConfig.get().custom_stylesheet.read(), valid_css)  # form success should have updated model

        # Second case, existing file input can be cleared / removed
        form_data['custom_stylesheet-clear'] = True  # select "clear" checkbox

        self.assertEqual(SiteConfig.get().custom_stylesheet.read(), valid_css)  # assert file was saved and attached
        form = SiteConfigForm(form_data, files={}, instance=self.config, is_deck_owner=True)
        self.assertTrue(form.is_valid())
        form.save()
        # assert there is no saved files, ie. "reading" non-existing file should raise an exception
        with self.assertRaises(ValueError):
            SiteConfig.get().custom_stylesheet.read()
