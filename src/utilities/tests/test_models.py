from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from utilities.models import ImageResource, VideoResource


class UtilitiesModelStrTest(SimpleTestCase):
    """__str__ rendering for the utilities media models (ImageResource / VideoResource)."""

    def test_image_resource_str__returns_name(self):
        """ImageResource is represented by its name."""
        self.assertEqual(str(ImageResource(name="School Logo")), "School Logo")

    def test_video_resource_str__combines_title_and_file(self):
        """VideoResource is represented as 'title: <video_file>', including the filename when a file is attached."""
        video = VideoResource(title="Intro", video_file=SimpleUploadedFile("intro.mp4", b"data"))
        self.assertEqual(str(video), "Intro: intro.mp4")

    def test_video_resource_str__empty_file_part_when_no_file(self):
        """With no attached file, the file part of the representation is empty."""
        self.assertEqual(str(VideoResource(title="Intro")), "Intro: ")
