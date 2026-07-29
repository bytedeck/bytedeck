from django.test import SimpleTestCase

from utilities.models import ImageResource, VideoResource


class UtilitiesModelStrTest(SimpleTestCase):
    """__str__ rendering for the utilities media models (ImageResource / VideoResource)."""

    def test_image_resource_str__returns_name(self):
        """ImageResource is represented by its name."""
        self.assertEqual(str(ImageResource(name="School Logo")), "School Logo")

    def test_video_resource_str__combines_title_and_file(self):
        """VideoResource is represented as 'title: <video_file>' (empty file part when none is attached)."""
        self.assertEqual(str(VideoResource(title="Intro")), "Intro: ")
