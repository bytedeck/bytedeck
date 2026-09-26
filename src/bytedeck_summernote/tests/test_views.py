import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from django_summernote.models import Attachment
from model_bakery import baker
from PIL import Image

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class TestByteDeckSummernoteView(ByteDeckTenantTestCase):
    def test_url__editor_view_responds(self):
        """Customized view class is configured and respond"""
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "foobar"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)


class TestByteDeckSummernoteUploadAttachment(ByteDeckTenantTestCase):
    """The editor's image upload, at the url the editor posts to (django_summernote-upload_attachment)."""

    @classmethod
    def setUpClass(cls):
        """Isolate MEDIA_ROOT in a per-run temp dir so the uploaded images don't land in the project's media dir."""
        cls._temp_media = tempfile.mkdtemp(prefix='test-media-summernote-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._temp_media, ignore_errors=True)
        super().setUpClass()

    def setUp(self):
        """Sign in as a student: anyone signed in may add an image to an editor, such as a submission's comment box."""
        self.client.force_login(baker.make(User))

    def image(self):
        """A one-pixel PNG, which Summernote's upload form accepts as an image."""
        png = io.BytesIO()
        Image.new("RGB", (1, 1)).save(png, "PNG")
        return SimpleUploadedFile("image.png", png.getvalue(), content_type="image/png")

    def test_upload__saves_the_image_whatever_else_is_posted(self):
        """The editor posts the textarea's data-* attributes with the image, and a browser add-on can put its own there.

        The accessiBe overlay marks elements data-acsb-navigable, data-acsb-now-navigable and data-acsb-hidden,
        which the editor posts as these three fields. django-summernote's view passed each posted field to
        attachment.save(), so the upload failed with "save() got an unexpected keyword argument 'acsbNavigable'" (#1555).
        """
        response = self.client.post(
            reverse("django_summernote-upload_attachment"),
            {"files": self.image(), "acsbNavigable": "true", "acsbNowNavigable": "false", "acsbHidden": "true"},
        )

        self.assertEqual(response.status_code, 200)
        attachment = Attachment.objects.get()
        self.assertEqual(response.json()["files"][0]["url"], attachment.file.url)
